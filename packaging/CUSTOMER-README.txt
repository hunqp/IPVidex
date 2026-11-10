IPVidex - IP Video Protocol Utility
Windows 10 / 11, 64-bit

GETTING STARTED
  Installer:          run IPVidex-Setup.exe and start IPVidex from the Start menu.
  Single executable:  copy IPVidex.exe anywhere and run it. The first start
                      takes a few seconds while it unpacks its runtime.
  Portable folder:    keep every file of the folder together and run
                      IPVidex.exe inside it.

  Python and VLC are bundled; nothing else needs to be installed.

NETWORK
  ONVIF and RTSP need network access to the cameras.
  When the RTMP or P2P server starts, Windows Firewall may ask for permission;
  allow it on the private network the cameras are connected to.

PRIVACY
  Passwords are never saved. Only stream URLs (without credentials), the RTSP
  user name and the certificate path are remembered between sessions.

FILES CREATED BY THE APPLICATION
  Error log:                %LOCALAPPDATA%\IPVidex\logs
  Server TLS certificates:  %LOCALAPPDATA%\IPVidex\tls
  Remembered fields:        HKEY_CURRENT_USER\Software\IPVidex\IPVidex

LICENSE
  Copyright (C) 2026 Vivoo. IPVidex is free software released under the
  GNU General Public License version 3 and comes with NO WARRANTY.
  See LICENSE.txt for the full terms.

SECURITY WARNINGS
  If this release is not digitally signed, Windows SmartScreen may show
  "Windows protected your PC". Choose "More info" > "Run anyway" only if you
  obtained the file from a trusted source. Smart App Control blocks unsigned
  applications entirely.
