"""ตรวจว่า IP อยู่ในช่วง IP (CIDR) ของมหาวิทยาลัยหรือไม่"""

import ipaddress


def parse_network(text):
    """CIDR (หรือ IP เดี่ยว) -> network, ใช้ไม่ได้คืน None"""
    try:
        return ipaddress.ip_network((text or "").strip(), strict=False)
    except ValueError:
        return None


def split_lines(text):
    """textarea (หนึ่งช่วงต่อบรรทัด) -> รายการช่วงที่ตัดช่องว่างและข้ามบรรทัดว่าง"""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def ip_in_networks(ip, networks):
    """True เมื่อ ip อยู่ในช่วงใดช่วงหนึ่ง; ip หรือช่วงที่อ่านไม่ได้ถือว่าไม่ตรง"""
    try:
        address = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    for text in networks or []:
        network = parse_network(text)
        if network is not None and network.version == address.version and address in network:
            return True
    return False
