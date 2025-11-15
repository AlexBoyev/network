# Networking Layers Simulator (L1 / L2 / L3)

This project is a Python-based home-network simulator that shows what happens on Open Systems Interconnection (OSI) Layers 1–3 inside a small home LAN.

- 🧱 L1 (Physical): cables, ports, NICs, raw bits on the wire  
- 🔁 L2 (Data Link): Ethernet frames, MAC learning, broadcast vs unicast  
- 🌐 L3 (Network): IP addresses, DHCP, ARP, and IP packet delivery  

Everything is logged step by step so you can follow the exact path from one device to another.

---

## Topology (from devices.yaml)

### Router

- Name: `home_router`  
- Model: `Star Pro`  
- Interfaces:

| Logical IF | MAC               | IP         | Mask           | DHCP Range              |
|------------|-------------------|------------|----------------|-------------------------|
| wan        | 02:aa:aa:aa:00:01 | (no IP yet) | (unused)      | none                    |
| lan1       | 02:aa:aa:aa:10:01 | 10.0.10.1  | 255.255.255.0 | 10.0.10.100–10.0.10.200 |
| lan2       | 02:aa:aa:aa:20:01 | 10.0.20.1  | 255.255.255.0 | 10.0.20.100–10.0.20.200 |
| lan3       | 02:aa:aa:aa:30:01 | 10.0.30.1  | 255.255.255.0 | 10.0.30.100–10.0.30.200 |
| lan4       | 02:aa:aa:aa:40:01 | 10.0.40.1  | 255.255.255.0 | 10.0.40.100–10.0.40.200 |

Currently, the simulation uses:

- lan1 for the Office LAN (10.0.10.0/24)  
- lan2 for the Living Room LAN (10.0.20.0/24)  
- lan3 and lan4 are defined but unused for now.

### Switches

- 🟦 `office_switch` – Office Switch (TP-Link Office 4-port, pure L2)  
- 🟦 `living_room_switch` – Living Room Switch (TP-Link Living Room 4-port, pure L2)

### End Devices

Office LAN (lan1, 10.0.10.0/24):

- ☎ `phone_1` – Office Phone, MAC 02:cc:10:00:00:10  
- 💻 `office_pc` – Office PC, MAC 02:cc:10:00:00:20  
- 🖨️ `printer` – Office Printer, MAC 02:cc:10:00:00:30  

Living Room LAN (lan2, 10.0.20.0/24):

- 📱 `phone_2` – Living Room Phone, MAC 02:cc:20:00:00:10  
- 📺 `tv` – Living Room TV, MAC 02:cc:20:00:00:20  

Both LAN1 and LAN2 now use DHCP to get dynamic IP addresses from the router.

---

## Topology Diagram (ASCII)

```text
                             ┌───────────────────────────────┐
                             │        Home Router             │
                             │          (Star Pro)            │
                             │                               │
                             │  lan1: 10.0.10.1/24 (DHCP)     │
                             │  lan2: 10.0.20.1/24 (DHCP)     │
                             │  wan: (unused)                 │
                             └───────────┬───────────┬────────┘
                                         │           │
                                         │           │
                                         │           │
                                         │           │
                    ┌────────────────────┘           └────────────────────┐
                    │                                                     │
                    ▼                                                     ▼

        ┌───────────────────────────┐                     ┌───────────────────────────┐
        │       Office Switch       │                     │   Living Room Switch      │
        │      (TP-Link 4-port)     │                     │      (TP-Link 4-port)     │
        ├─────────┬─────────┬──────┬──────┤             ├─────────┬─────────┬──────┬──────┤
        │  p1     │  p2     │ p3   │ p4   │             │  p1     │  p2     │ p3   │ p4   │
        │ uplink  │ phone_1 │ PC   │ prntr│             │ uplink  │ phone_2 │ TV   │ free │
        └─────────┴─────────┴──────┴──────┘             └─────────┴─────────┴──────┴──────┘

```

Important:

- Each switch connects directly to the router, not to each other.  
- Office devices live on 10.0.10.0/24 (lan1).  
- Living room devices live on 10.0.20.0/24 (lan2).  

---

## Simulation Phases (driver.py)

The main script is `network/driver.py`. When you run it, it performs these phases.

### Phase 1 – Build L1 Topology (Physical)

- Load `devices.yaml`.  
- Create router, switches, and end devices.  
- Create cables and connect:
  - Router lan1 to Office Switch uplink.
  - Router lan2 to Living Room Switch uplink.
  - Office Phone, Office PC, Printer to Office Switch ports.
  - Living Room Phone and TV to Living Room Switch ports.
- Apply MAC addresses from YAML to router interfaces, switch ports, and NICs.

Logs look like:

- `Cable | Star Pro->port1 plugged`  
- `NIC created with MAC ...`  
- `L2 config: overriding NIC MAC ... from YAML`  

At the end of this phase, everything is wired but only at the physical level.

### Phase 2 – Power On Devices

- Power on router, both switches, and all end devices.  
- L1 is now fully active: links are up, ports are on, but no switching or IP logic is running yet.

### Phase 3 – Enable L2 Switching on All Switches

- Call `enable_l2(True)` on both switches.  
- Switches start to:
  - Learn source MAC to incoming port mapping.  
  - Flood frames for broadcast and unknown unicast.  
  - Unicast frames once the destination MAC is known.

You will see logs such as:

- `L2: learned 02:cc:10:00:00:10 is on TP-Link Office 4-port->port2`  
- `L2: broadcast flood ...`  
- `FLOW: DeviceA -> DeviceB payload=...`

### Phase 4 – Configure Router L3 Interfaces from YAML

For each logical interface (`lan1` and `lan2`) that is wired:

- Override interface MAC with the value from YAML.  
- Assign the IP address and netmask from YAML.  
- Register a connected route for the subnet.

Example log:

- `Router Home Router: configured Star Pro->port1 ip=10.0.10.1 mask=255.255.255.0`  
- `Router Home Router: configured Star Pro->port2 ip=10.0.20.1 mask=255.255.255.0`  

At this point, the router knows:

- 10.0.10.0/24 is directly connected on lan1.  
- 10.0.20.0/24 is directly connected on lan2.  

### Phase 5 – Attach DHCP Services (lan1 and lan2)

The driver now attaches DHCP pools for both subnets:

- LAN1 pool: 10.0.10.100–10.0.10.200, gateway 10.0.10.1.  
- LAN2 pool: 10.0.20.100–10.0.20.200, gateway 10.0.20.1.

Internally, two DHCPPool objects are created (one per subnet) and registered on the router so that the router can respond to DHCP requests on both lan1 and lan2.

### Phase 6 – DHCP For All Devices On LAN1 And LAN2

The driver now makes all devices that should be dynamic act like real DHCP clients:

- On LAN1 (Office LAN):
  - `phone_1` requests an IP.  
  - `office_pc` requests an IP.  
  - `printer` requests an IP.

- On LAN2 (Living Room LAN):
  - `phone_2` requests an IP.  
  - `tv` requests an IP.

In the logs you will see each device:

- Sending a broadcast `DHCP_DISCOVER` (destination MAC ff:ff:ff:ff:ff:ff).  
- The Office or Living Switch flooding it.  
- The router receiving it on the proper interface and allocating an IP from the correct pool.  
- The device applying the `IP / Mask / Gateway` from the router's `DHCP_ACK`.

Expected result (typical first run allocation):

- `phone_1`  -> 10.0.10.100  
- `office_pc` -> 10.0.10.101  
- `printer`   -> 10.0.10.102  
- `phone_2`  -> 10.0.20.100  
- `tv`        -> 10.0.20.101  

### Phase 7 – ARP And L3 Unicast Demo (office_pc -> printer)

Finally, the driver demonstrates L3 communication between two hosts on the same subnet (Office LAN):

1. `office_pc` wants to send an IP packet to `printer` (10.0.10.101 -> 10.0.10.102).  
2. It checks that both are in the same subnet (10.0.10.0/24).  
3. Since it does not know the printer's MAC yet, it sends an ARP Request (broadcast).  
4. Printer sees the ARP Request for its IP and replies with its MAC address.  
5. `office_pc` caches this in its ARP table.  
6. `office_pc` sends an IP packet to `printer` using destination MAC 02:cc:10:00:00:30.  
7. The switch forwards the frame only to the printer port.  
8. Printer decapsulates the frame, reads the IP header, and logs that it received the payload.

The logs clearly show ARP and IP behavior at each step.

---

## How To Run

From the project root:

```bash
python -m network.driver
```

Or, depending on your layout:

```bash
python network/driver.py
```

You will see the phases:

- Phase 1: Build L1 topology  
- Phase 2: Power on devices  
- Phase 3: Enable L2 switching  
- Phase 4: Configure router L3 interfaces  
- Phase 5: Attach DHCP services for lan1 and lan2  
- Phase 6: DHCP for all LAN devices  
- Phase 7: ARP + IP demo from office_pc to printer  

---

## Future Ideas (WAN And Beyond)

- Add a real WAN interface on the router with a public IP.  
- Simulate an "Internet cloud" on the other side, with a simple listener server.  
- Implement NAT on the router so internal devices (10.0.x.x) can talk to the WAN listener.  
- Add ICMP ping simulation, TCP/UDP flows, and timeouts.  
- Add more L3 tests: office_pc to tv (cross-subnet via router), or between multiple LANs.

This project is meant to be a learning playground for L1/L2/L3 behavior using simple Python objects and rich logs.
