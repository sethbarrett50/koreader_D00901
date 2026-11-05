# USBNetwork: SSH into a K3 over USB

USBNetwork turns the USB cable into a network link, so you can `ssh root@192.168.2.2` into the
Kindle. The battery reader ([battery.md](battery.md)) needs it.

## Installing it

- On a new unit: install with `--usbnet` (or tick the box in the TUI).
- On a unit that already has KOReader: `koreader-d00901 --only usbnet`. This stages only the
  USBNetwork update.

## Turning it on

On the Kindle's search bar:

1. Type `;debugOn` and press Enter.
2. Type `~usbNetwork` and press Enter.
3. Type `;debugOff` and press Enter.

The Kindle stops being a USB drive and appears on the computer as a network interface, often `usb0`
(check with `ip link`). Assign the computer's side its address:

```
sudo ip addr add 192.168.2.1/24 dev usb0
sudo ip link set usb0 up
```

(The older equivalent is `sudo ifconfig usb0 192.168.2.1`.) Then:

```
ssh root@192.168.2.2
```

Login is passwordless only over USB with Wi-Fi mode off.

## Back to USB drive mode

Bring the interface down with `sudo ip link set usb0 down`, then enter `~usbNetwork` again on the
Kindle.

## Six units, one address

Every unit uses 192.168.2.2 but has its own SSH host key, so plain `ssh` warns about a changed host
key when you switch units. Either remove the old key (`ssh-keygen -R 192.168.2.2`) or connect with
`-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`, which is what
`koreader-d00901-battery` does for this point-to-point USB link.
