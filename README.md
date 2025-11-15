
# Networking Layers Simulator (L1 / L2 / L3)

This project is a **Python-based network simulator** that models how real NICs, switches, and routers behave across OSI Layers 1–3:

- **L1 – Physical:** bits on cables, ports, connectivity  
- **L2 – Data Link:** Ethernet frames, MAC addressing, switching, flooding  
- **L3 – Network:** DHCP, ARP, IP routing, subnets, gateway behaviour  

Everything that happens in the logs is a **slowed-down version of a real LAN**.  
Your home router + switch + devices perform all these steps in microseconds in hardware; here you see each step clearly.

---

# 🖥️ Current Topology

```
         (L3 Router + DHCP Server)
                [ Star Pro ]
             iface: r1-p1
        MAC: 02:9d:e2:6d:e2:9f
        IP:  10.0.0.1/24
                  |
                  | Star Pro->port1  (router interface)
                  | Archer AX53->port4 (switch uplink)
                  |
        +----------------------------+
        |   TP-Link Archer AX53     |   (L2 Switch)
        |   sw1                     |
        |   no IP (pure L2 device)  |
        +----------------------------+
          | p1         | p2         | p3
          |            |            |
   host1.nic      host2.nic    host3.nic
 (Alex-PC)       (Phone)       (Printer)

host1 MAC: 02:f9:13:53:c9:30  
host2 MAC: 02:d2:a7:14:9f:6d  
host3 MAC: 02:4c:61:c7:77:2f
```

Subnet: `10.0.0.0/24`  
Gateway: `10.0.0.1`

---

# 🔌 Layer 1 – Physical Layer
- Cables, ports, power-on, raw bit transmission.

# 🔁 Layer 2 – Data Link Layer (Ethernet)
- MAC learning  
- Broadcast flooding  
- Unknown-unicast flooding  
- Unicast forwarding  

# 🌐 Layer 3 – Network Layer (IP, ARP, DHCP)
- DHCP server on router  
- Hosts get IPs dynamically  
- ARP resolves IP → MAC  
- IP unicast delivery  

---


# 🌍 WAN Interface (Future Feature)
Currently only LAN side exists.  
Future: add second router interface + default route + ISP simulation + NAT.

---

# ▶️ Running
```
python driver.py
```
