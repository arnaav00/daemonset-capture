#!/usr/bin/env python3
"""
Kubernetes DaemonSet Traffic Monitor
Captures API endpoint requests/responses at the node level
"""

import json
import socket
import struct
import sys
import time
import os
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import subprocess
import threading
import queue

# Try to import scapy for packet capture, fallback to raw sockets
try:
    from scapy.all import sniff, IP, TCP, UDP, Raw, get_if_list
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    get_if_list = None
    print("WARNING: scapy not available, using raw socket capture", file=sys.stderr)

class TrafficMonitor:
    def __init__(self, output_file: str = "/tmp/endpoints.json", node_name: str = None):
        self.output_file = output_file
        self.node_name = node_name or os.environ.get('NODE_NAME', 'unknown-node')
        self.endpoints = []
        self.endpoint_lock = threading.Lock()
        self.http_connections = {}  # Track HTTP connections
        self.tcp_streams = {}  # Track TCP streams for reassembly
        self.output_queue = queue.Queue()
        self.running = True
        
        # Start output writer thread
        self.writer_thread = threading.Thread(target=self._write_outputs, daemon=True)
        self.writer_thread.start()
        
    def _write_outputs(self):
        """Write captured endpoints to file periodically"""
        while self.running:
            try:
                endpoint = self.output_queue.get(timeout=5)
                if endpoint:
                    self._write_endpoint(endpoint)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing endpoint: {e}", file=sys.stderr)
    
    def _write_endpoint(self, endpoint: Dict):
        """Write single endpoint to JSON file"""
        try:
            with open(self.output_file, 'a') as f:
                f.write(json.dumps(endpoint) + '\n')
            # Also print to stdout for kubectl logs
            print(f"ENDPOINT_CAPTURE: {json.dumps(endpoint)}")
        except Exception as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
    
    def _is_complete_http_message(self, data: bytes) -> bool:
        """Check if data contains a complete HTTP message (headers at minimum)"""
        # HTTP headers end with \r\n\r\n
        if b'\r\n\r\n' not in data:
            return False
        return True
    
    def _parse_http_request(self, data: bytes, src_ip: str, dst_ip: str, src_port: int, dst_port: int) -> Optional[Dict]:
        """Parse HTTP request from packet data"""
        try:
            # Look for HTTP methods
            if not (data.startswith(b'GET') or data.startswith(b'POST') or 
                    data.startswith(b'PUT') or data.startswith(b'DELETE') or
                    data.startswith(b'PATCH') or data.startswith(b'HEAD') or
                    data.startswith(b'OPTIONS')):
                return None
            
            # Check if we have complete headers
            if not self._is_complete_http_message(data):
                return None
            
            # Parse HTTP request
            lines = data.split(b'\r\n')
            if not lines:
                return None
            
            # Parse request line
            request_line = lines[0].decode('utf-8', errors='ignore')
            parts = request_line.split()
            if len(parts) < 2:
                return None
            
            method = parts[0]
            path = parts[1]
            version = parts[2] if len(parts) > 2 else 'HTTP/1.1'
            
            # Parse headers
            headers = {}
            body_start = 0
            for i, line in enumerate(lines[1:], 1):
                if not line:
                    body_start = i + 1
                    break
                if b':' in line:
                    key, value = line.split(b':', 1)
                    headers[key.decode('utf-8', errors='ignore').strip()] = \
                        value.decode('utf-8', errors='ignore').strip()
            
            host = headers.get('Host', dst_ip)
            if ':' in str(dst_port) and dst_port != 80 and dst_port != 443:
                host = f"{host}:{dst_port}"
            
            endpoint_data = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node": self.node_name,
                "method": method,
                "endpoint": path,
                "full_url": f"http://{host}{path}",
                "host": host,
                "protocol": "HTTP",
                "source_ip": src_ip,
                "source_port": src_port,
                "destination_ip": dst_ip,
                "destination_port": dst_port,
                "request_headers": headers,
                "version": version
            }
            
            return endpoint_data
        except Exception as e:
            # Silently fail - not all packets are HTTP
            return None
    
    def _parse_http_response(self, data: bytes, src_ip: str, dst_ip: str, 
                            src_port: int, dst_port: int, connection_key: str) -> Optional[Dict]:
        """Parse HTTP response from packet data"""
        try:
            if not data.startswith(b'HTTP/'):
                return None
            
            # Check if we have complete headers
            if not self._is_complete_http_message(data):
                return None
            
            lines = data.split(b'\r\n')
            if not lines:
                return None
            
            # Parse status line
            status_line = lines[0].decode('utf-8', errors='ignore')
            parts = status_line.split(maxsplit=2)
            if len(parts) < 2:
                return None
            
            version = parts[0]
            status_code = int(parts[1])
            status_text = parts[2] if len(parts) > 2 else ''
            
            # Parse headers
            headers = {}
            body_start = 0
            for i, line in enumerate(lines[1:], 1):
                if not line:
                    body_start = i + 1
                    break
                if b':' in line:
                    key, value = line.split(b':', 1)
                    headers[key.decode('utf-8', errors='ignore').strip()] = \
                        value.decode('utf-8', errors='ignore').strip()
            
            # Try to match with request if available
            request_info = self.http_connections.get(connection_key, {})
            
            endpoint_data = {
                "id": str(uuid.uuid4()),
                "type": "response",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node": self.node_name,
                "method": request_info.get("method", "UNKNOWN"),
                "endpoint": request_info.get("endpoint", "/"),
                "full_url": f"http://{request_info.get('host', dst_ip)}{request_info.get('endpoint', '/')}",
                "host": request_info.get("host", dst_ip),
                "protocol": "HTTP",
                "status_code": status_code,
                "status_text": status_text,
                "source_ip": src_ip,
                "source_port": src_port,
                "destination_ip": dst_ip,
                "destination_port": dst_port,
                "response_headers": headers,
                "version": version
            }
            
            return endpoint_data
        except Exception as e:
            return None
    
    def _reassemble_tcp_stream(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int, 
                               data: bytes, seq: int):
        """Reassemble TCP stream to handle multi-packet HTTP requests/responses"""
        # Create connection keys for both directions
        key1 = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
        key2 = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
        
        # Use the key that doesn't have data yet, or the one we're adding to
        if key1 not in self.tcp_streams and key2 not in self.tcp_streams:
            # New connection, use key1
            stream_key = key1
            self.tcp_streams[stream_key] = bytearray()
            self.tcp_streams[stream_key + "_seq"] = seq
        elif key1 in self.tcp_streams:
            stream_key = key1
        else:
            stream_key = key2
        
        # Append data to stream
        if stream_key not in self.tcp_streams:
            self.tcp_streams[stream_key] = bytearray()
        self.tcp_streams[stream_key].extend(data)
        
        # Try to parse complete HTTP messages
        stream_data = bytes(self.tcp_streams[stream_key])
        
        # Look for complete HTTP request/response
        # HTTP ends with \r\n\r\n (headers) and potentially body
        return stream_data
    
    def _process_tcp_data(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int, data: bytes):
        """Process TCP payload data for HTTP parsing"""
        connection_key = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
        reverse_key = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
        
        # First, try to get complete stream from reassembly
        complete_data = data
        if connection_key in self.tcp_streams:
            complete_data = bytes(self.tcp_streams[connection_key])
        elif reverse_key in self.tcp_streams:
            complete_data = bytes(self.tcp_streams[reverse_key])
        
        # Try parsing as HTTP request first
        endpoint = self._parse_http_request(complete_data, src_ip, dst_ip, src_port, dst_port)
        if endpoint:
            self.http_connections[connection_key] = {
                "method": endpoint["method"],
                "endpoint": endpoint["endpoint"],
                "host": endpoint["host"]
            }
            self.output_queue.put(endpoint)
            # Clear the stream after successful parse
            if connection_key in self.tcp_streams:
                del self.tcp_streams[connection_key]
            if reverse_key in self.tcp_streams:
                del self.tcp_streams[reverse_key]
            return
        
        # Try parsing as HTTP response
        endpoint = self._parse_http_response(complete_data, src_ip, dst_ip, src_port, dst_port, reverse_key)
        if endpoint:
            self.output_queue.put(endpoint)
            # Clear the stream after successful parse
            if connection_key in self.tcp_streams:
                del self.tcp_streams[connection_key]
            if reverse_key in self.tcp_streams:
                del self.tcp_streams[reverse_key]
            return
    
    def _process_packet_scapy(self, packet):
        """Process packet using scapy"""
        try:
            if not packet.haslayer(IP):
                return
            
            ip_layer = packet[IP]
            src_ip = ip_layer.src
            dst_ip = ip_layer.dst
            
            if packet.haslayer(TCP):
                tcp_layer = packet[TCP]
                src_port = tcp_layer.sport
                dst_port = tcp_layer.dport
                seq = tcp_layer.seq
                
                # Check for HTTP traffic (ports 80, 8080, 8000, etc.)
                http_ports = [80, 443, 8080, 8000, 3000, 5000, 8443, 9000]
                is_http_port = dst_port in http_ports or src_port in http_ports
                
                # Check if this is internal Kubernetes traffic (pod IPs)
                is_pod_traffic = (src_ip.startswith('10.244.') or dst_ip.startswith('10.244.') or 
                                 src_ip.startswith('10.96.') or dst_ip.startswith('10.96.'))
                
                # Debug: Log HTTP port traffic with more detail (especially internal IPs)
                if is_http_port:
                    has_raw = packet.haslayer(Raw)
                    raw_len = len(packet[Raw].load) if has_raw else 0
                    # Log pod traffic (10.244.x.x pod IPs or 10.96.x.x service IPs) very prominently
                    if is_pod_traffic:
                        print(f"*** POD TRAFFIC ***: {src_ip}:{src_port} -> {dst_ip}:{dst_port} (has_raw={has_raw}, raw_len={raw_len})", file=sys.stderr, flush=True)
                
                if is_http_port:
                    # Always track HTTP port connections for reassembly
                    connection_key = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
                    reverse_key = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
                    
                    if packet.haslayer(Raw):
                        data = packet[Raw].load
                        if len(data) > 0:
                            # Try reassembly first
                            stream_data = self._reassemble_tcp_stream(src_ip, src_port, dst_ip, dst_port, data, seq)
                            
                            # Process the stream data
                            if len(stream_data) > 4:  # Minimum for HTTP
                                self._process_tcp_data(src_ip, src_port, dst_ip, dst_port, stream_data)
                    else:
                        # TCP packet without Raw layer - might be part of a larger stream
                        # Store connection info for later reassembly
                        if connection_key not in self.tcp_streams:
                            self.tcp_streams[connection_key] = bytearray()
                                
        except Exception as e:
            # Log errors but continue - not all packets are parseable
            print(f"Error processing packet: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            pass
    
    def _capture_raw_socket(self):
        """Fallback packet capture using raw sockets"""
        try:
            # Create raw socket
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            
            print("Starting raw socket capture (requires root privileges)...", file=sys.stderr)
            
            while self.running:
                try:
                    packet, addr = s.recvfrom(65565)
                    
                    # Parse IP header (first 20 bytes)
                    ip_header = struct.unpack('!BBHHHBBH4s4s', packet[:20])
                    src_ip = socket.inet_ntoa(ip_header[8])
                    dst_ip = socket.inet_ntoa(ip_header[9])
                    protocol = ip_header[6]
                    
                    if protocol == 6:  # TCP
                        # Parse TCP header (starts at byte 20)
                        if len(packet) > 40:
                            tcp_header = struct.unpack('!HHLLBBHHH', packet[20:40])
                            src_port = tcp_header[0]
                            dst_port = tcp_header[1]
                            
                            # Extract payload
                            data_offset = (tcp_header[4] >> 4) * 4
                            if len(packet) > 20 + data_offset:
                                data = packet[20 + data_offset:]
                                
                                # Check for HTTP
                                if dst_port in [80, 8080, 8000, 3000, 5000] or src_port in [80, 8080, 8000, 3000, 5000]:
                                    connection_key = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
                                    reverse_key = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
                                    
                                    endpoint = self._parse_http_request(data, src_ip, dst_ip, src_port, dst_port)
                                    if endpoint:
                                        self.http_connections[connection_key] = {
                                            "method": endpoint["method"],
                                            "endpoint": endpoint["endpoint"],
                                            "host": endpoint["host"]
                                        }
                                        self.output_queue.put(endpoint)
                                    else:
                                        endpoint = self._parse_http_response(data, src_ip, dst_ip,
                                                                             src_port, dst_port, reverse_key)
                                        if endpoint:
                                            self.output_queue.put(endpoint)
                except socket.error:
                    continue
                except Exception as e:
                    print(f"Error processing packet: {e}", file=sys.stderr)
                    continue
        except PermissionError:
            print("ERROR: Raw socket capture requires root privileges", file=sys.stderr)
            print("Please run with CAP_NET_RAW capability or as root", file=sys.stderr)
            sys.exit(1)
    
    def start(self):
        """Start traffic monitoring"""
        print(f"Starting traffic monitor on node: {self.node_name}", file=sys.stderr, flush=True)
        print(f"Output file: {self.output_file}", file=sys.stderr, flush=True)
        print(f"SCAPY_AVAILABLE: {SCAPY_AVAILABLE}", file=sys.stderr, flush=True)
        
        # Initialize output file
        try:
            with open(self.output_file, 'w') as f:
                f.write('')  # Clear/initialize file
            print(f"Initialized output file: {self.output_file}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Warning: Could not initialize output file: {e}", file=sys.stderr, flush=True)
        
        if SCAPY_AVAILABLE:
            print("Using scapy for packet capture", file=sys.stderr, flush=True)
            try:
                # Get interface list first
                print("Getting interface list...", file=sys.stderr, flush=True)
                interfaces = get_if_list()
                print(f"Available interfaces: {interfaces}", file=sys.stderr, flush=True)
                
                # Filter for HTTP traffic on common ports
                filter_str = "tcp and (port 80 or port 443 or port 8080 or port 8000 or port 3000 or port 5000 or port 8443 or port 9000)"
                print(f"Using filter: {filter_str}", file=sys.stderr, flush=True)
                
                # Collect interfaces to capture on
                capture_interfaces = []
                for iface in interfaces:
                    if iface == 'lo':
                        continue  # Skip loopback
                    # Capture on veth interfaces (pod traffic), eth0 (host), and bridge interfaces
                    # veth* interfaces are critical for pod-to-pod traffic
                    if (iface.startswith('veth') or iface == 'eth0' or 
                        iface.startswith('docker') or iface.startswith('br') or
                        iface.startswith('cni') or iface.startswith('flannel')):
                        capture_interfaces.append(iface)
                
                # If no specific interfaces found, capture on all except loopback
                if not capture_interfaces:
                    capture_interfaces = [iface for iface in interfaces if iface != 'lo']
                
                print(f"Capturing on {len(capture_interfaces)} interfaces: {capture_interfaces}", file=sys.stderr, flush=True)
                
                # If we have interfaces, use threaded capture on all of them
                # This ensures we catch pod-to-pod traffic on veth interfaces
                if len(capture_interfaces) > 0:
                    def capture_interface(iface):
                        try:
                            print(f"Starting capture on interface: {iface}", file=sys.stderr, flush=True)
                            sniff(iface=iface, prn=self._process_packet_scapy, store=False, 
                                  stop_filter=lambda x: not self.running, filter=filter_str)
                        except Exception as e:
                            print(f"Error capturing on {iface}: {e}", file=sys.stderr, flush=True)
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                    
                    if len(capture_interfaces) == 1:
                        # Single interface - no threading needed
                        print(f"Capturing on single interface: {capture_interfaces[0]}", file=sys.stderr, flush=True)
                        sniff(iface=capture_interfaces[0], prn=self._process_packet_scapy, store=False, 
                              stop_filter=lambda x: not self.running, filter=filter_str)
                    else:
                        # Multiple interfaces - use threading
                        print(f"Starting capture on {len(capture_interfaces)} interfaces using threads", file=sys.stderr, flush=True)
                        threads = []
                        for iface in capture_interfaces:
                            t = threading.Thread(target=capture_interface, args=(iface,), daemon=True)
                            t.start()
                            threads.append(t)
                            time.sleep(0.5)  # Small delay between thread starts
                        
                        print("All capture threads started, monitoring traffic...", file=sys.stderr, flush=True)
                        
                        # Keep main thread alive
                        while self.running:
                            time.sleep(1)
                    return
                
                # Fallback to 'any' interface if no specific interfaces found
                print("No specific interfaces found, trying 'any' interface...", file=sys.stderr, flush=True)
                try:
                    sniff(iface=None, prn=self._process_packet_scapy, store=False, 
                          stop_filter=lambda x: not self.running, filter=filter_str)
                    return
                except Exception as e:
                    print(f"ERROR: Failed to capture on 'any' interface: {e}", file=sys.stderr, flush=True)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                
                # If still empty, try capturing on 'any'
                if not capture_interfaces:
                    capture_interfaces = [iface for iface in interfaces if iface != 'lo']
                
                print(f"Capturing on interfaces: {capture_interfaces}", file=sys.stderr, flush=True)
                
                # Filter for HTTP traffic on common ports
                filter_str = "tcp and (port 80 or port 443 or port 8080 or port 8000 or port 3000 or port 5000 or port 8443 or port 9000)"
                print(f"Using filter: {filter_str}", file=sys.stderr, flush=True)
                
                # Capture on multiple interfaces using threads
                def capture_interface(iface):
                    try:
                        print(f"Starting capture on interface: {iface}", file=sys.stderr, flush=True)
                        sniff(iface=iface, prn=self._process_packet_scapy, store=False, 
                              stop_filter=lambda x: not self.running, filter=filter_str)
                    except Exception as e:
                        print(f"Error capturing on {iface}: {e}", file=sys.stderr, flush=True)
                        import traceback
                        traceback.print_exc(file=sys.stderr)
                
                if len(capture_interfaces) == 1:
                    # Single interface - no threading needed
                    print(f"Capturing on single interface: {capture_interfaces[0]}", file=sys.stderr, flush=True)
                    sniff(iface=capture_interfaces[0], prn=self._process_packet_scapy, store=False, 
                          stop_filter=lambda x: not self.running, filter=filter_str)
                else:
                    # Multiple interfaces - use threading
                    print(f"Starting capture on {len(capture_interfaces)} interfaces using threads", file=sys.stderr, flush=True)
                    threads = []
                    for iface in capture_interfaces:
                        t = threading.Thread(target=capture_interface, args=(iface,), daemon=True)
                        t.start()
                        threads.append(t)
                        time.sleep(0.5)  # Small delay between thread starts
                    
                    print("All capture threads started, monitoring traffic...", file=sys.stderr, flush=True)
                    
                    # Keep main thread alive
                    while self.running:
                        time.sleep(1)
                        
            except Exception as e:
                print(f"ERROR with scapy capture: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc(file=sys.stderr)
                print("Falling back to raw socket capture", file=sys.stderr, flush=True)
                self._capture_raw_socket()
        else:
            print("Using raw socket capture (scapy not available)", file=sys.stderr, flush=True)
            self._capture_raw_socket()
    
    def stop(self):
        """Stop traffic monitoring"""
        self.running = False

def main():
    # Get node name from environment or hostname
    node_name = os.environ.get('NODE_NAME') or os.environ.get('HOSTNAME', 'unknown-node')
    output_file = os.environ.get('OUTPUT_FILE', '/tmp/endpoints.json')
    
    monitor = TrafficMonitor(output_file=output_file, node_name=node_name)
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        monitor.stop()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
