#!/usr/bin/env python3
"""
Script to create SUMO network with multiple traffic lights
"""

import os
import subprocess

def create_nodes():
    """Create nodes.nod.xml with multiple intersections"""
    nodes_content = '''<?xml version="1.0" encoding="UTF-8"?>
<nodes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/nodes_file.xsd">
    <!-- Main intersections -->
    <node id="C" x="200" y="200" type="traffic_light"/>
    <node id="N" x="200" y="400" type="traffic_light"/>
    <node id="S" x="200" y="0" type="traffic_light"/>
    <node id="E" x="400" y="200" type="traffic_light"/>
    <node id="W" x="0" y="200" type="traffic_light"/>
    
    <!-- Additional intersections -->
    <node id="NE" x="400" y="400" type="traffic_light"/>
    <node id="NW" x="0" y="400" type="traffic_light"/>
    <node id="SE" x="400" y="0" type="traffic_light"/>
    <node id="SW" x="0" y="0" type="traffic_light"/>
    
    <!-- Boundary nodes -->
    <node id="N_out" x="200" y="600" type="priority"/>
    <node id="S_out" x="200" y="-200" type="priority"/>
    <node id="E_out" x="600" y="200" type="priority"/>
    <node id="W_out" x="-200" y="200" type="priority"/>
</nodes>'''
    
    with open('nodes.nod.xml', 'w') as f:
        f.write(nodes_content)
    print("✅ Created nodes.nod.xml with 9 traffic lights")

def create_edges():
    """Create edges.edg.xml"""
    edges_content = '''<?xml version="1.0" encoding="UTF-8"?>
<edges xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/edges_file.xsd">
    <!-- Main grid edges -->
    <edge id="C2N" from="C" to="N" priority="3" numLanes="2" speed="13.9"/>
    <edge id="N2C" from="N" to="C" priority="3" numLanes="2" speed="13.9"/>
    <edge id="C2S" from="C" to="S" priority="3" numLanes="2" speed="13.9"/>
    <edge id="S2C" from="S" to="C" priority="3" numLanes="2" speed="13.9"/>
    <edge id="C2E" from="C" to="E" priority="3" numLanes="2" speed="13.9"/>
    <edge id="E2C" from="E" to="C" priority="3" numLanes="2" speed="13.9"/>
    <edge id="C2W" from="C" to="W" priority="3" numLanes="2" speed="13.9"/>
    <edge id="W2C" from="W" to="C" priority="3" numLanes="2" speed="13.9"/>
    
    <!-- Additional connections -->
    <edge id="N2NE" from="N" to="NE" priority="2" numLanes="1" speed="11.1"/>
    <edge id="NE2N" from="NE" to="N" priority="2" numLanes="1" speed="11.1"/>
    <edge id="E2NE" from="E" to="NE" priority="2" numLanes="1" speed="11.1"/>
    <edge id="NE2E" from="NE" to="E" priority="2" numLanes="1" speed="11.1"/>
    
    <!-- Boundary connections -->
    <edge id="N2N_out" from="N" to="N_out" priority="1" numLanes="2" speed="13.9"/>
    <edge id="N_out2N" from="N_out" to="N" priority="1" numLanes="2" speed="13.9"/>
    <edge id="S2S_out" from="S" to="S_out" priority="1" numLanes="2" speed="13.9"/>
    <edge id="S_out2S" from="S_out" to="S" priority="1" numLanes="2" speed="13.9"/>
    <edge id="E2E_out" from="E" to="E_out" priority="1" numLanes="2" speed="13.9"/>
    <edge id="E_out2E" from="E_out" to="E" priority="1" numLanes="2" speed="13.9"/>
    <edge id="W2W_out" from="W" to="W_out" priority="1" numLanes="2" speed="13.9"/>
    <edge id="W_out2W" from="W_out" to="W" priority="1" numLanes="2" speed="13.9"/>
</edges>'''
    
    with open('edges.edg.xml', 'w') as f:
        f.write(edges_content)
    print("✅ Created edges.edg.xml")

def create_connections():
    """Create connections.con.xml"""
    connections_content = '''<?xml version="1.0" encoding="UTF-8"?>
<connections xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/connections_file.xsd">
    <!-- Connections will be auto-generated -->
</connections>'''
    
    with open('connections.con.xml', 'w') as f:
        f.write(connections_content)
    print("✅ Created connections.con.xml")

def build_network():
    """Build the network using netconvert"""
    try:
        cmd = [
            'netconvert',
            '--node-files', 'nodes.nod.xml',
            '--edge-files', 'edges.edg.xml',
            '--connection-files', 'connections.con.xml',
            '--output-file', 'network_multi.net.xml',
            '--tls.guess', 'true',
            '--tls.default-type', 'static'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Network built successfully: network_multi.net.xml")
            return True
        else:
            print(f"❌ Network build failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("❌ netconvert not found. Make sure SUMO is installed and in PATH")
        return False

def main():
    """Main function"""
    print("🚧 Creating SUMO network with multiple traffic lights...")
    
    create_nodes()
    create_edges()
    create_connections()
    
    if build_network():
        print("\n🎉 Multi-intersection network created!")
        print("📁 Files created:")
        print("   - nodes.nod.xml")
        print("   - edges.edg.xml") 
        print("   - connections.con.xml")
        print("   - network_multi.net.xml")
        print("\n💡 To use: Replace 'network.net.xml' with 'network_multi.net.xml' in simulation.sumocfg")
    else:
        print("\n❌ Network creation failed")

if __name__ == "__main__":
    main()