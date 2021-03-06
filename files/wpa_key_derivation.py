#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Modified by: Julien Quartier & Nathan Séville


Derive WPA keys from Passphrase and 4-way handshake info

Calcule un MIC d'authentification (le MIC pour la transmission de données
utilise l'algorithme Michael. Dans ce cas-ci, l'authentification, on utilise
sha-1 pour WPA2 ou MD5 pour WPA)
"""

__author__      = "Abraham Rubinstein et Yann Lederrey"
__copyright__   = "Copyright 2017, HEIG-VD"
__license__ 	= "GPL"
__version__ 	= "1.0"
__email__ 		= "abraham.rubinstein@heig-vd.ch"
__status__ 		= "Prototype"

from scapy.all import *
from binascii import a2b_hex, b2a_hex
# from pbkdf2_math import pbkdf2_hex
from pbkdf2 import *
from numpy import array_split
from numpy import array
import hmac, hashlib

def customPRF512(key,A,B):
    """
    This function calculates the key expansion from the 256 bit PMK to the 512 bit PTK
    """
    blen = 64
    i    = 0
    R    = b''
    while i<=((blen*8+159)/160):
        hmacsha1 = hmac.new(key,A+str.encode(chr(0x00))+B+str.encode(chr(i)),hashlib.sha1)
        i+=1
        R = R+hmacsha1.digest()
    return R[:blen]

# Read capture file -- it contains beacon, authentication, associacion, handshake and data
wpa=rdpcap("wpa_handshake.cap") 

# Transform mac from string with semicolon to binary string
def normalizeMac(mac):
    return a2b_hex(mac.replace(":", ""))


# Return an array of SSIDs found in packets. 
def findSSIDs(packets):
    SSIDs = []

    for packet in packets: 
        # The SSID is advertized in Beacons
        if Dot11Beacon in packet and Dot11Elt in packet[Dot11Beacon]:
            packet = packet[Dot11Beacon]
            packet = packet[Dot11Elt]
            if packet.ID == 0: # SSID
                SSIDs.append(packet.info.decode())

    return SSIDs

# Return list a APs MACs found in packets
def getAPMACs(packets):
    MACs = []

    for packet in packets: 
        # Only ap sends beacons. So we know it's an ap
        if Dot11Beacon in packet and Dot11Elt in packet[Dot11Beacon]:
            MACs.append(normalizeMac(packet.addr2))

    return MACs


# Return a list of clients MACs
def findClients(packets):
    MACs = []

    for packet in packets:
        if Dot11Auth in packet:
            # Client start authentication with AP. seqnum = 2 so we know that the client MAC is addr1
            if packet[Dot11Auth].seqnum == 2:
                MACs.append(normalizeMac(packet.addr1))

    return MACs


# Return a list of nonce emitted from a specific MAC
def findNonce(packets, sourceMac):
    nonces = []

    for packet in packets:
        # Nonces can be found in EAPOL frames
        if EAPOL in packet and normalizeMac(packet.addr2) == sourceMac:
            # Extract nonce from raw value
            nonces.append(packet[Raw].load[13:45])
    return nonces

# Return a list of MICs emitted from a specific MAC
def findMiC(packets, sourceMac):
    mics = []

    for packet in packets:
        if EAPOL in packet and normalizeMac(packet.addr2) == sourceMac:
            mics.append(packet[Raw].load[77:-2])
    return mics


# Important parameters for key derivation - most of them can be obtained from the pcap file
passPhrase  = "actuelle"
A           = "Pairwise key expansion" #this string is used in the pseudo-random function
ssid        = findSSIDs(wpa)[0]
APmac       = getAPMACs(wpa)[0]
Clientmac   = findClients(wpa)[0]

# Authenticator and Supplicant Nonces
ANonce      = findNonce(wpa, APmac)[0]
SNonce      = findNonce(wpa, Clientmac)[0]


# This is the MIC contained in the 4th frame of the 4-way handshake
# When attacking WPA, we would compare it to our own MIC calculated using passphrases from a dictionary
mic_to_test = b2a_hex(findMiC(wpa, Clientmac)[1])

B           = min(APmac,Clientmac)+max(APmac,Clientmac)+min(ANonce,SNonce)+max(ANonce,SNonce) #used in pseudo-random function

data        = a2b_hex("0103005f02030a0000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000") #cf "Quelques détails importants" dans la donnée

print ("\n\nValues used to derivate keys")
print ("============================")
print ("Passphrase: ",passPhrase,"\n")
print ("SSID: ",ssid,"\n")
print ("AP Mac: ",b2a_hex(APmac),"\n")
print ("CLient Mac: ",b2a_hex(Clientmac),"\n")
print ("AP Nonce: ",b2a_hex(ANonce),"\n")
print ("Client Nonce: ",b2a_hex(SNonce),"\n")

#calculate 4096 rounds to obtain the 256 bit (32 oct) PMK
passPhrase = str.encode(passPhrase)
ssid = str.encode(ssid)
pmk = pbkdf2(hashlib.sha1,passPhrase, ssid, 4096, 32)

#expand pmk to obtain PTK
ptk = customPRF512(pmk,str.encode(A),B)

#calculate MIC over EAPOL payload (Michael)- The ptk is, in fact, KCK|KEK|TK|MICK
mic = hmac.new(ptk[0:16],data,hashlib.sha1)


print ("\nResults of the key expansion")
print ("=============================")
print ("PMK:\t\t",pmk.hex(),"\n")
print ("PTK:\t\t",ptk.hex(),"\n")
print ("KCK:\t\t",ptk[0:16].hex(),"\n")
print ("KEK:\t\t",ptk[16:32].hex(),"\n")
print ("TK:\t\t",ptk[32:48].hex(),"\n")
print ("MICK:\t\t",ptk[48:64].hex(),"\n")
print ("MIC:\t\t",mic.hexdigest(),"\n")
