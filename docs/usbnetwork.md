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

Over USB with Wi-Fi off, any password is accepted.

### If SSH hangs or times out

- **The interface is gone** (`ip -br addr` no longer lists it): USBNetwork is off. A restart turns it
  off, and `~usbNetwork` is a toggle, so running it a second time also turns it off. Run the three
  search-bar commands again.
- **The interface is there but has no 192.168.2.1:** NetworkManager removes addresses it did not
  set. Tell it to leave the interface alone, then add the address again:

  ```
  nmcli device set usb0 managed no
  sudo ip addr add 192.168.2.1/24 dev usb0
  ping -c 2 192.168.2.2
  ```

  The interface name may differ (for example `enxee4900000000`); use the one `ip -br link` shows.
- **Commands behave oddly on the Kindle:** it runs BusyBox 1.7 from 2012. `grep -E` is not
  supported, and `date -s` does not accept `YYYY-MM-DD`. Copy files to the computer and work there
  instead, for example `ssh root@192.168.2.2 'cat /var/log/messages' > k3-messages.log`.

## Back to USB drive mode

Bring the interface down with `sudo ip link set usb0 down`, then enter `~usbNetwork` again on the
Kindle.

## Six units, one address

Every unit uses 192.168.2.2 but has its own SSH host key, so plain `ssh` warns about a changed host
key when you switch units. Either remove the old key (`ssh-keygen -R 192.168.2.2`) or connect with
`-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`, which is what
`koreader-d00901-battery` does for this point-to-point USB link.
