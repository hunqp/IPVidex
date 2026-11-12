# Hướng dẫn build IPVidex

## Build đơn giản: một file EXE chạy trực tiếp

Mở **PowerShell** tại thư mục dự án và chạy:

```powershell
.\build.cmd
```

Script tự đóng gói ứng dụng. Khi hoàn tất, mở file này hoặc gửi cho người dùng:

```text
dist\IPVidex.exe
```

Người dùng không cần cài Python hoặc VLC: chúng đã được đóng gói sẵn.
Không cần kích hoạt venv hoặc cài Inno Setup cho kiểu build này.

Nếu PowerShell đang ở thư mục khác, chạy `cd D:\IPVidex` trước.
Nếu dùng **Git Bash**, lệnh tương đương là `./build.cmd`.

## Chuẩn bị lần đầu trên máy build

Cài các phần mềm sau một lần:

- Python 3.10 trở lên, bản 64-bit.
- VLC 3.x, bản 64-bit, tại `C:\Program Files\VideoLAN\VLC`.
- Chỉ khi cần bộ cài Setup: cài Inno Setup 6 vào thư mục mặc định hoặc thêm `ISCC.exe` vào PATH.

Sau đó chạy từng dòng trong PowerShell tại thư mục dự án:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Nếu đã có venv và các thư viện, bỏ qua bước tạo venv. Cài lại requirements khi chúng thay đổi.

## Các kiểu build khác (tùy chọn)

| Muốn tạo | Lệnh PowerShell | Kết quả |
|---|---|---|
| Bộ cài đặt (cần Inno Setup 6) | `.\build.cmd -Mode installer` | `dist\IPVidex-Setup.exe` |
| Một EXE chạy trực tiếp | `.\build.cmd -Mode onefile` | `dist\IPVidex.exe` |
| Thư mục portable | `.\build.cmd -Mode onedir` | `dist\IPVidex\` |

Với portable, gửi nguyên thư mục, bao gồm `_internal`.
Các bản build dùng chung `dist`; chỉ gửi đúng kết quả của lần build vừa thành công.

Nếu VLC được cài ở nơi khác:

```powershell
.\build.cmd -Mode installer -VlcDirectory "D:\Apps\VLC"
```

`build.cmd` gọi `packaging\Build.ps1` với chính sách chạy script chỉ áp dụng cho tiến trình build.
Cách gọi trực tiếp `Build.ps1` vẫn hoạt động; mặc định của script đó vẫn là `onefile`.

## Kiểm tra trước khi phát hành

Đồng bộ phiên bản trong `core\Version.py`, `AppVersion` trong `packaging\Installer.iss`, badge README và `CHANGELOG.md`.
Chạy từng dòng:

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m ruff check .
```

Sau khi build bộ cài hoặc portable, kiểm tra runtime (với onefile, dùng đường dẫn dist\IPVidex.exe):

```powershell
dist\IPVidex\IPVidex.exe --check-runtime | Out-String
Start-Process dist\IPVidex\IPVidex.exe -ArgumentList --self-test -Wait -PassThru
```

Runtime cần báo `"available": true`; self-test cần có ExitCode bằng 0.
Thử bộ cài trên máy sạch: tìm và đăng nhập camera, phát video trực tiếp, khởi động RTMP server.
Đóng ứng dụng và kiểm tra không còn tiến trình `IPVidex.exe` hoặc `mediamtx.exe`.

## Khi gặp lỗi

- Thiếu Inno Setup: cài Inno Setup 6 rồi chạy lại `build.cmd`.
- Thiếu venv: thực hiện phần chuẩn bị lần đầu ở trên.
- Thiếu VLC: cài VLC 3.x 64-bit hoặc chỉ định `-VlcDirectory`.
- PyInstaller thất bại: kiểm tra lỗi trong terminal và cài lại `requirements-dev.txt` nếu thiếu thư viện. Bộ cài chỉ được tạo khi bước build thành công.

## Ký số

Build chưa được ký số có thể bị Windows SmartScreen cảnh báo hoặc Smart App Control chặn.
Để ký bản phát hành: build `onedir`, dùng `signtool` ký các file `.exe`, `.dll`, `.pyd` trong `dist\IPVidex`, biên dịch `packaging\Installer.iss` bằng Inno Setup, rồi ký `dist\IPVidex-Setup.exe`.
Không chạy lại `build.cmd` sau khi ký payload vì lệnh này sẽ build lại ứng dụng.

