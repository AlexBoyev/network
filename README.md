# Networking Layers Simulator (L1 / L2 / L3)

This project is a Python-based home-network simulator that demonstrates OSI Layers 1–3:

- L1 – Physical: Cables, ports, NICs
- L2 – Data Link: Ethernet frames, MAC learning, broadcast/unicast
- L3 – Network: DHCP, ARP, IP delivery, routing decisions

No emojis or special characters are used in this README.

---

# Topology (from devices.yaml)

Router: home_router (Star Pro)  
Switches:
- office_switch (TP-Link Office 4-port)
- living_room_switch (TP-Link Living Room 4-port)

End devices:
- phone_1
- office_pc
- printer
- phone_2
- tv

Router LAN interfaces:

| Interface | MAC              | IP         | Mask          | DHCP Range            |
|-----------|------------------|------------|----------------|------------------------|
| lan1      | 02:aa:aa:aa:10:01 | 10.0.10.1  | 255.255.255.0 | 10.0.10.100–10.0.10.200 |
| lan2      | 02:aa:aa:aa:20:01 | 10.0.20.1  | 255.255.255.0 | 10.0.20.100–10.0.20.200 |
| lan3      | 02:aa:aa:aa:30:01 | 10.0.30.1  | 255.255.255.0 | (unused)               |
| lan4      | 02:aa:aa:aa:40:01 | 10.0.40.1  | 255.255.255.0 | (unused)               |

---

# Topology Diagram (ASCII Only)

```
                 Home Router (Star Pro)
           +----------------------------------+
           | lan1: 10.0.10.1/24 (Office LAN)  |
           | lan2: 10.0.20.1/24 (Living LAN)  |
           +--------------+-------------------+
                          |                   
                          |                   
                (Router port1)         (Router port2)
                          |                   |
                          |                   |
        Office Switch (L2 Only)      Living Room Switch (L2 Only)
        +--------+--------+--------+    +--------+--------+--------+
        | p1     | p2     | p3     |    | p1     | p2     | p3     |
        | uplink | phone_1| office |    | uplink | phone_2|  tv    |
        |        |        |  pc    |    |        |        |        |
        +--------+--------+--------+    +--------+--------+--------+
                  p4: printer                  p4: (unused)
```

Both switches connect directly to the router, not to each other.

---

# Simulation Flow (Driver)

1. Phase 1: Build L1  
   - Create cables, NICs, ports  
   - Apply MAC addresses from YAML  
   - Connect all links

2. Phase 2: Power on devices  
   - Router, switches, end devices turned ON

3. Phase 3: Enable L2 switching  
   - MAC learning  
   - Flooding for unknown unicast and broadcast  
   - Unicast when MAC is known

4. Phase 4: Configure router L3 interfaces  
   - Assign IP, masks  
   - Build connected routes  
   - Initialize ARP tables

5. Phase 5: Attach DHCP on lan1  
   - Pool: 10.0.10.100–10.0.10.200

6. Phase 6: DHCP Assignment  
   - phone_1 → 10.0.10.100  
   - office_pc → 10.0.10.101  
   - printer → 10.0.10.102  

7. Phase 7: ARP + L3 Delivery  
   - office_pc ARPs for printer  
   - Printer replies with ARP Reply  
   - office_pc sends IP packet to printer  
   - Printer receives and logs it

---

# Run

```
python -m network.driver
```

---

# Future Improvements

- DHCP on LAN2  
- Inter-subnet routing example  
- ICMP ping simulation  
- NAT example  

