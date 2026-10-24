# Secure mobile checkout on the local network

Flask intentionally blocks customer order API calls from another device over HTTP. Checkout sends a private per-order access token, so do not use `http://<computer-ip>:5000`, disable the HTTPS guard, or paste the token into a URL. Running `python app.py` without TLS stays loopback-only; Flask now refuses to bind a non-loopback address unless both TLS files are configured.

The application reads these exact TLS variables in `app.py`:

- `FLASK_TLS_CERT_FILE`: path to the server certificate.
- `FLASK_TLS_KEY_FILE`: path to the matching server private key.

When both are set, the development server starts with TLS. The mobile launcher binds Flask only to the current Wi-Fi IPv4 address, rather than all interfaces. `TRUSTED_PROXY_HOPS` is not required for this direct-to-Flask setup. The `.env.example` loopback default is intentionally not phone-accessible; do not change it to `0.0.0.0`.

## 1. Install mkcert

Run in PowerShell:

```powershell
winget install --id FiloSottile.mkcert --exact --source winget
```

Close that PowerShell window, open a new one, change to the project directory, and confirm installation:

```powershell
Set-Location 'C:\Users\shiva\OneDrive\Documents\Desktop\Natural-Language-Robot'
mkcert -version
```

The package identifier was checked in the Windows Package Manager source. `mkcert` is a local development certificate tool; it does not use Firebase or a paid service.

## 2. Confirm the trusted Wi-Fi profile, generate the certificate, and start Flask

Only continue when this computer is connected to the restaurant's trusted Wi-Fi. Check the current profile and address; do not assume a previous IP is still current:

```powershell
Get-NetConnectionProfile -InterfaceAlias 'Wi-Fi' |
    Select-Object InterfaceAlias, Name, NetworkCategory
Get-NetIPAddress -InterfaceAlias 'Wi-Fi' -AddressFamily IPv4 |
    Where-Object {
        $_.AddressState -eq 'Preferred' -and
        $_.IPAddress -notlike '169.254.*'
    } |
    Select-Object InterfaceAlias, IPAddress, PrefixLength
```

The Wi-Fi connection must show `NetworkCategory` as `Private`. Only after verifying that it is the restaurant's trusted network, an administrator can mark it Private:

```powershell
Set-NetConnectionProfile -InterfaceAlias 'Wi-Fi' -NetworkCategory Private
```

Do not mark public, guest, or unfamiliar Wi-Fi as Private. The startup script rejects non-private profiles and non-RFC-1918 addresses.

From the project directory, start the application using the provided script:

```powershell
Set-Location 'C:\Users\shiva\OneDrive\Documents\Desktop\Natural-Language-Robot'
$lanIp = (Get-NetIPAddress -InterfaceAlias 'Wi-Fi' -AddressFamily IPv4 |
    Where-Object {
        $_.AddressState -eq 'Preferred' -and
        $_.IPAddress -notlike '169.254.*'
    } |
    Select-Object -First 1 -ExpandProperty IPAddress)
Write-Host "Current Wi-Fi IPv4: $lanIp"
.\scripts\start-mobile-https.ps1 -LanIp $lanIp
```

The script validates the address is assigned to a Private interface, installs mkcert's public root CA into the current Windows user's trust store, creates a new IP-SAN certificate and uniquely named private key under `%LOCALAPPDATA%\Natural-Language-Robot\certs` without overwriting an existing certificate key, configures Flask's existing TLS variables, and binds Flask only to that Wi-Fi IP on port 5000. It also sets the six customer QR URLs to HTTPS for this run. Leave this terminal open while testing. Omitting `-LanIp` auto-detects an interface with a Private default route. The server does not listen on other interfaces or use plain HTTP.

If the LAN IP changes, rerun the script with the new address; mkcert will generate a matching certificate. The server certificate and key are not stored in the repository. Confirm the certificate SAN in another PowerShell window:

```powershell
$certDir = Join-Path $env:LOCALAPPDATA 'Natural-Language-Robot\certs'
$certFile = Get-ChildItem $certDir -Filter 'lan-*.pem' |
    Where-Object { $_.Name -notlike 'lan-key-*' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 -ExpandProperty FullName
certutil -dump $certFile | Select-String -Pattern 'Subject Alternative Name|IP Address|DNS Name'
```

The certificate should list the current LAN IP. Confirm both files exist without displaying their contents:

```powershell
$certSuffix = [IO.Path]::GetFileNameWithoutExtension($certFile).Substring(4)
$keyFile = Join-Path $certDir "lan-key-$certSuffix.pem"
Test-Path $certFile
Test-Path $keyFile
```

Both commands should print `True`.

## 3. Install and trust the public mkcert CA on your own phone

The phone must trust the local CA, otherwise its browser should reject the HTTPS connection. Use a private transfer such as a USB cable; do not serve the CA file through Flask or an unauthenticated network share.

The startup script exports the public root CA to `%LOCALAPPDATA%\Natural-Language-Robot\certs\mkcert-rootCA.cer` and adds it to the current Windows user's root store. Transfer **only this public CA certificate** to your phone:

```powershell
$certDir = Join-Path $env:LOCALAPPDATA 'Natural-Language-Robot\certs'
$phoneCaFile = Join-Path $certDir 'mkcert-rootCA.cer'
Test-Path $phoneCaFile
```

Transfer `mkcert-rootCA.cer` to your own phone over USB. Do **not** copy or share `rootCA-key.pem` or any `lan-key-*.pem` file; never put either private key in the repository, email, messaging app, or phone.

- **Android:** open the device's Security settings and use **Install a certificate** / **CA certificate** to install the transferred certificate. Names vary by Android version/vendor. Approve the system warning only after confirming this is your own computer's mkcert CA. Chrome should then trust certificates issued by this local CA.
- **iPhone/iPad:** open the transferred `.cer` to install its configuration profile. Then go to **Settings → General → About → Certificate Trust Settings** and enable full trust for the installed mkcert root. Remove that profile and trust setting when you no longer need this local test CA.

Installing a root CA grants it trust on that device; only do this on your own test phone, and only for the CA created on your computer.

## 4. Open the HTTPS checkout

Once the phone trusts the certificate and the script is running, open this exact checkout URL:

```text
https://<current-wifi-ip>:5000/customer/checkout?table=1
```

For the QR test, open the admin login on the restaurant computer, sign in, then open **Tables & QR codes** and scan the displayed **Table 1** QR code with the phone:

```powershell
Start-Process "https://${lanIp}:5000/admin"
```

If not already signed in, the existing Firebase authentication sends you to the admin login first. The admin QR page renders all six links as `https://<current-wifi-ip>:5000/customer/menu?table=1` through `table=6`. Do not use `http://`; customer order requests require HTTPS, a valid per-order access token, and a same-origin `Origin` header, supplied by the checkout page.

## 5. Check Windows Firewall and permit only the private LAN

Windows Firewall must be enabled. Inspect existing inbound Python rules before adding another rule:

```powershell
Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound |
    Where-Object { $_.DisplayName -eq 'python.exe' } |
    ForEach-Object {
        $rule = $_
        $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule
        $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
        [pscustomobject]@{
            Name = $rule.Name
            Profile = $rule.Profile
            Action = $rule.Action
            Program = $app.Program
            Protocol = $port.Protocol
            LocalPort = $port.LocalPort -join ','
            RemoteAddress = $address.RemoteAddress -join ','
        }
    } | Format-Table -AutoSize
```

If the phone cannot connect, open **PowerShell as Administrator**, verify the Wi-Fi network is trusted and Private, and add a narrowly scoped allow rule plus a Public-profile block for TCP 5000:

```powershell
$projectPython = 'C:\Users\shiva\OneDrive\Documents\Desktop\Natural-Language-Robot\.venv\Scripts\python.exe'
New-NetFirewallRule `
    -DisplayName 'Natural-Language-Robot HTTPS (Private LAN only)' `
    -Program $projectPython -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 5000 -Profile Private -RemoteAddress LocalSubnet
New-NetFirewallRule `
    -DisplayName 'Natural-Language-Robot HTTPS (Block Public)' `
    -Direction Inbound -Action Block -Protocol TCP -LocalPort 5000 `
    -Profile Public -RemoteAddress Any
```

On this computer, Windows also currently has broad inbound allow rules named `python.exe` for the system Python on the Public profile (TCP and UDP, any local port, any remote address). Review those rules using the command above. If they are not needed for another service, disable the identified rules; do not leave a broad Public Python rule in place as a substitute for the scoped TCP 5000 rules. Never create a router port forward or a public tunnel.

To disable only broad Public-profile Allow rules for the current system Python executable that permit any port from any remote address, first inspect the rules this selects, then run the final line as Administrator:

```powershell
$broadPublicPythonRules = Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound |
    Where-Object {
        $_.DisplayName -eq 'python.exe' -and
        $_.Action -eq 'Allow' -and
        $_.Profile.ToString() -match 'Public'
    } |
    ForEach-Object {
        $rule = $_
        $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule
        $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
        if (
            $app.Program -match '\\python(?:\d+)?\.exe$' -and
            @($port.LocalPort) -contains 'Any' -and
            @($address.RemoteAddress) -contains 'Any'
        ) {
            $rule
        }
    }
$broadPublicPythonRules | Format-Table Name, DisplayName, Profile, Action
$broadPublicPythonRules | Disable-NetFirewallRule
```

To remove the two app-specific rules when finished testing:

```powershell
Remove-NetFirewallRule -DisplayName 'Natural-Language-Robot HTTPS (Private LAN only)'
Remove-NetFirewallRule -DisplayName 'Natural-Language-Robot HTTPS (Block Public)'
```

The computer and phone must be connected to the same trusted Wi-Fi. Guest Wi-Fi, VLAN separation, wireless client/AP isolation, or router access-control rules can prevent devices from reaching one another; ask the network administrator to allow trusted Wi-Fi clients to communicate locally. A local-network QR scan does not prove a person is physically inside the restaurant.

## 6. Verify the saved order

The browser should show a secure connection without a certificate warning. Place a small demo order. When Firestore confirms the save, the site redirects to the confirmation page and displays the generated `QR-...` order ID and `Order Placed` status. The Flask log should show `POST /api/customer/orders` with HTTP status `201`. You can also confirm it appears in the admin order list.

The order is written to the existing `customer_orders` collection with a server-generated unique ID, server-validated table/menu items and total, server timestamp, initial status, and a hash of the customer's access token. The Firestore server uses create-only writes and the browser reuses its idempotency key when retrying from the same checkout tab, so a retry after a lost response returns the same order instead of creating another one. These are demo orders; they are not sent to restaurant staff, payment processing, or a physical robot.

## Troubleshooting

- **Browser says the certificate is not private / secure:** do not bypass the warning. Verify that the phone trusts this computer's mkcert root CA, that the certificate SAN includes the current Wi-Fi IP, and that the URL uses that exact IP and port.
- **Wi-Fi address changed:** rerun step 2 with the newly assigned IP, reinstall/trust the mkcert root on the phone only if the CA changed, and restart Flask with the newly generated certificate and key.
- **Phone cannot open the page:** ensure Flask is running with `FLASK_HOST` set to the current Wi-Fi IP, both TLS variables are set, the Wi-Fi profile is Private only because it is trusted, the phone and computer are on the same non-isolated Wi-Fi, and the scoped Private-profile firewall rule allows port 5000.
- **Checkout still says HTTPS is required:** inspect the browser address bar. It must start with `https://` and use the current Wi-Fi IP. Confirm the TLS startup script is still running and printed an HTTPS health address. The order token is intentionally not sent by this application to a LAN HTTP endpoint.
- **Flask returns HTTP 503 or logs a Firestore error:** HTTPS has reached the server; inspect the Flask log and existing Firebase/Firestore configuration. Do not put credentials in this guide or paste them into a browser.
- **Network drops after tapping Place:** retry from the same checkout tab so its idempotency key remains the same. After a successful response, use the displayed order ID/confirmation. Do not clear browser site data while recovering an uncertain request.

## Automated versus phone verification

Run the focused automated route/QR tests from the project directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_customer_qr_ordering.py'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_firestore_orders.py'
```

These tests verify all six menu and checkout table URLs, generation of six table-specific HTTPS QR images, and order submission with each supported table number. Firestore is replaced with an in-memory fake in these tests; they do not touch existing Firestore orders. They do not prove Wi-Fi reachability, router isolation settings, phone certificate trust, or successful physical scanning.

For the manual phone check, connect the phone to the restaurant Wi-Fi, trust the local CA as described above, scan the Table 1 QR displayed in **Tables & QR codes**, and verify that the menu, cart, and checkout all load with Table 1. Submitting the demo order writes a new demo record to the existing Firestore collection, so do that only when you intend to create a test order. No successful phone scan or real Firestore order has been verified by the automated tests.

The Flask development server is intended for local testing, not public deployment. For production, use a production WSGI server and a correctly configured TLS reverse proxy.

## Temporary phone demo with a Cloudflare Quick Tunnel

This is temporary public internet access, not local-Wi-Fi-only access. Anyone who receives the current random `trycloudflare.com` URL can open the menu and attempt customer orders. Successful orders are saved to the existing Firestore collection. The public tunnel is restricted in Flask to customer menu/cart/checkout/order pages, customer menu/order APIs, the customer CSS/JavaScript, and menu-upload images. Admin, analytics, diagnostics, and robot/simulation routes are denied on the public hostname. Order creation also keeps same-origin/access-token/idempotency checks, revalidates table/menu/quantity/prices, caps the JSON request at 32 KB, and is limited to 10 attempts per Cloudflare client IP per 10 minutes. Stop both processes immediately after the demonstration.

Do not add a router port forward. Flask must remain bound to `127.0.0.1`; Cloudflare provides HTTPS externally and connects to the local HTTP listener. The randomly generated tunnel address changes every time the tunnel restarts, so refresh `PUBLIC_DEMO_URL` and `QR_BASE_URL`, restart Flask, and regenerate the QR page each time.

### 1. Install the official Cloudflare client once

In PowerShell:

```powershell
winget install --id Cloudflare.cloudflared --exact --source winget --accept-source-agreements
```

Open a new PowerShell window and confirm it is available:

```powershell
cloudflared --version
```

### 2. Start the temporary tunnel in Terminal A

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

Wait for Cloudflare to print a URL like `https://random-words.trycloudflare.com`. Leave Terminal A running and copy that HTTPS URL. Do not use any URL from an earlier tunnel session.

### 3. Start Flask in Terminal B with that exact URL

Replace the example URL below with the current URL from Terminal A:

```powershell
Set-Location 'C:\Users\shiva\OneDrive\Documents\Desktop\Natural-Language-Robot'
$publicUrl = 'https://random-words.trycloudflare.com'

$env:PUBLIC_DEMO_MODE = '1'
$env:PUBLIC_DEMO_URL = $publicUrl
$env:QR_BASE_URL = $publicUrl
$env:FLASK_HOST = '127.0.0.1'
$env:PORT = '5000'
$env:FLASK_DEBUG = '0'
$env:FLASK_TLS_CERT_FILE = ''
$env:FLASK_TLS_KEY_FILE = ''
$env:TRUSTED_PROXY_HOPS = '1'

.\.venv\Scripts\python.exe .\app.py
```

Flask validates that both public URLs are the same `https://*.trycloudflare.com` origin and refuses to start public-demo mode unless it is loopback-bound with exactly one trusted proxy hop.

### 4. Sign in locally and regenerate/verify all six QR codes

On the admin computer, open:

```powershell
Start-Process 'http://127.0.0.1:5000/admin'
```

Sign in using the existing admin authentication, open **Tables & QR codes**, and refresh the page. The six QR destinations must show the current tunnel URL with `table=1` through `table=6`. Scan Table 1 using a phone on mobile data or a different Wi-Fi; confirm the address bar has the current `https://...trycloudflare.com/customer/menu?table=1` address. Test the menu and checkout. An actual submit writes a new demo order to Firestore; only submit if that is intended.

### 5. Stop and disable the temporary public access

Press **Ctrl+C** in Terminal A to stop the tunnel, then **Ctrl+C** in Terminal B to stop Flask. Do not leave either terminal running when finished. The public URL then stops routing to this computer. When restarting the app normally in a new PowerShell window, do not set `PUBLIC_DEMO_MODE`, `PUBLIC_DEMO_URL`, `QR_BASE_URL`, or `TRUSTED_PROXY_HOPS`; local mode stays on `127.0.0.1`.

The automated public-demo tests verify the route allowlist, six QR destinations, order validation, and per-client rate limit. They do not prove that Cloudflare can establish a tunnel on this network or that a physical phone can scan it. Confirm those manually using the steps above.
