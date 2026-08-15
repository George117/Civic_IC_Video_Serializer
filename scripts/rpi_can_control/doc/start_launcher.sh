#!/bin/sh
# launcher.sh
# CAN0
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 sample-point 0.62 sjw 1 restart-ms 100
sudo ifconfig can0 txqueuelen 100
sudo ip link set can0 up
# CAN1
sudo ip link set can1 down
sudo ip link set can1 type can bitrate 125000 sample-point 0.75 sjw 2 restart-ms 100
sudo ifconfig can1 txqueuelen 100
sudo ip link set can1 up 

ifconfig