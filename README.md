# Học Trung

Ứng dụng PWA tự học tiếng Trung cho người Việt. Bạn có thể ôn nhanh 8 thẻ, nghe rảnh tay, dán ảnh hoặc văn bản từ tài liệu, tra nghĩa trong đoạn đọc và luyện viết trên máy tính.

Ứng dụng dùng khung **HSK 2.0** theo yêu cầu, với mục tiêu 2.500 mục từ HSK 1–5 và bài viết kiểu câu 99. Chinese Testing International công bố triển khai HSK 3.0 từ ngày 13/12/2026. Bạn có thể đối chiếu thể thức và đề cương của kỳ thi mình đăng ký. [Thông báo của CTI](https://old.chinesetest.cn/gonewcontent.do?flag=kdnew&id=51336883)

## Chạy bằng Docker Compose

Cần Docker với Compose v2. Mở terminal ở thư mục gốc của dự án.

```powershell
Copy-Item .env.example .env
```

Trên macOS hoặc Linux, dùng `cp .env.example .env`. Điền `GEMINI_API_KEY` trong `.env` để bật trích xuất tài liệu, tra nghĩa từ mới, tạo câu i+1 và chấm bài. `GEMINI_MODEL` mặc định là `gemini-2.5-flash`. Nếu tài khoản chưa có quyền dùng model này, đặt `GEMINI_MODEL=gemini-3.5-flash-lite`. [Lịch thay đổi model của Google](https://ai.google.dev/gemini-api/docs/deprecations#gemini-2.5-flash-models)

```sh
docker compose up --build -d
docker compose ps
```

Khi dịch vụ sẵn sàng, mở [Học Trung trên máy này](http://localhost:8080). Trong **Tiến độ HSK → Cài đặt**, bạn có thể xem trạng thái cơ sở dữ liệu, số từ trong danh mục, số tệp phát âm đã lưu và kiểm tra kết nối Gemini. Sau khi sửa khóa hoặc mô hình, chạy `docker compose up -d backend`.

Compose giữ PostgreSQL trong volume `postgres_data` và MP3 trong volume `audio_data` khi bạn dựng lại hoặc khởi động lại container. `docker compose logs -f backend` hiển thị quá trình khởi động. `docker compose down` dừng các dịch vụ và giữ dữ liệu.

## Mở trên điện thoại cùng Wi-Fi

1. Đặt `WEB_BIND_HOST=0.0.0.0` và `WEB_PORT=8080` trong `.env`, rồi chạy `docker compose up -d`. Bạn có thể đặt `WEB_BIND_HOST=127.0.0.1` khi chỉ dùng trên máy tính này.
2. Tìm địa chỉ IPv4 của máy chạy Docker ở mục Wi-Fi. Trên Windows, lệnh `ipconfig` hiển thị địa chỉ đó. Kết nối điện thoại vào cùng mạng rồi mở địa chỉ như `http://192.168.1.20:8080`, thay IP và cổng bằng giá trị của bạn.
3. Trên Android, mở menu trình duyệt và chọn **Thêm vào màn hình chính** hoặc **Cài đặt ứng dụng**. Trên iPhone, trong Safari chọn **Chia sẻ → Thêm vào màn hình chính**.

Điện thoại mở trực tiếp địa chỉ HTTP trong mạng Wi-Fi. Để dùng service worker và chế độ cài đặt PWA đầy đủ, mở ứng dụng qua HTTPS bằng tên máy và chứng chỉ được điện thoại tin cậy. Khi trình duyệt chỉ cung cấp lối tắt, biểu tượng vẫn mở được trang học. Bản Compose dành cho một người dùng trên mạng riêng. [Hướng dẫn cài PWA](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Installing)

## Sử dụng

1. Mở **Học hôm nay** và chọn **Học nhanh 2 phút**, một dạng bài, hoặc một buổi theo cấp độ và nguồn. Dùng `Space` để lật thẻ, `R` để nghe lại, `P` để hiện hoặc ẩn Pinyin và `1`–`4` để đánh giá mức nhớ. Khi cần nghe rảnh tay, chọn **Chế độ Học Lười**.
2. Ở **Nạp tài liệu**, thả một tệp hoặc nhấn `Ctrl+V` để trích xuất ảnh chụp hay văn bản đã sao chép. Sửa và chọn các mục trong bảng rồi bấm **Lưu vào kho ôn**. Trong **Thư viện tài liệu**, bạn có thể sửa tên, ghi chú và xóa một nguồn. Khi xóa nguồn, các mục từ, thẻ và lượt ôn được giữ lại. Để ôn một trang chiếu riêng, nạp ảnh hoặc tệp của trang đó thành nguồn riêng.
3. Mở **Luyện HSK 4–5** để làm bài cặp từ, viết đoạn 5 từ hoặc đọc và tra từ trực tiếp. Bấm vào một chữ Hán để xem bộ thủ, chiết tự và các từ HSK chứa chữ đó.
4. Mở **Từ điển & Cây chữ** hoặc nút chỉnh sửa trên thẻ để sửa từ, mẫu ngữ pháp và câu ví dụ đã lưu. Bạn có thể tạm bỏ từ khỏi hàng ôn và bật lại với lịch ôn cũ.
5. Xem độ phủ, dự báo và các từ hay sai trong **Tiến độ HSK**. Dự báo dùng số từ lần đầu được đánh giá từ mức **Nhớ được** trong 7 ngày gần nhất.

Định dạng nạp gồm PNG, JPG, WebP, PDF, PPTX/PPT, DOCX/DOC, XLSX, CSV và TXT. Giới hạn mặc định là 25 MiB mỗi tệp và 48 trang cho luồng ảnh. Trang được thu về tối đa 1.600 px mỗi chiều và trích xuất theo lô. Nội dung cần trích xuất hoặc chấm được gửi cho Gemini.

Edge TTS nhận văn bản tiếng Trung cần đọc, trả MP3 và ứng dụng lưu bản phát tại chỗ. Khi Edge TTS tạm gián đoạn, ứng dụng thử dùng giọng Quan thoại có sẵn trong trình duyệt. Danh sách nghe tiếp tục chuyển thẻ ngay cả khi thiết bị không phát được âm thanh. Bản cài PWA giữ giao diện trong cache. Các thao tác học và đồng bộ tiến độ cần kết nối tới backend.

## Sao lưu và khôi phục dữ liệu

1. Mở **Tiến độ HSK → Cài đặt → Sao lưu & Khôi phục dữ liệu** và chọn **Tải bản sao lưu (.json)**. Tệp chứa từ, mẫu câu, nguồn và liên kết, lịch FSRS, lượt ôn, bài viết và tùy chọn học.
2. Trên bản cài cần khôi phục, vào cùng mục, chọn **Khôi phục từ file sao lưu** và xác nhận. Ứng dụng kiểm tra định dạng, gộp dữ liệu trong một giao dịch và hiển thị số mục đã xử lý. Nhập lại cùng một tệp giữ nguyên số lượt ôn và nguồn.

Để tạo bản sao riêng của toàn bộ PostgreSQL, chạy lệnh sau từ thư mục dự án. Trên Windows, dùng Git Bash.

```sh
bash scripts/backup_postgres.sh
```

Script lưu tệp `.dump` vào thư mục `backups/`. Bạn có thể truyền một đường dẫn đích làm đối số. Tệp JSON dùng để khôi phục qua ứng dụng. Tệp `.dump` dùng với `pg_restore` khi quản trị PostgreSQL.

## Bổ sung từ vựng HSK

Lần khởi động mặc định nạp đủ 2.500 mục HSK 2.0 theo danh mục CTI, quy về 2.493 chữ viết giản thể duy nhất. Bộ mẫu có 182 từ đã chú giải, 25 mẫu ngữ pháp kèm câu ví dụ và 18 cặp từ dễ nhầm. Từ trùng chữ giản thể dùng chung thẻ và lịch ôn. Các mục mới chỉ có chữ Hán và Pinyin có thể được bổ sung nghĩa tiếng Việt trong Trình đọc hoặc nhập tiếp từ tệp. Đặt `SEED_FULL_HSK=false` nếu muốn bản cài mới bắt đầu với bộ mẫu. Tùy chọn này giữ nguyên các từ đã nạp. [Danh mục HSK 2.0 của CTI](https://old.chinesetest.cn/userfiles/file/HSK/HSK-2015.xlsx)

Chuẩn bị tệp CSV UTF-8 hoặc JSON. Các trường khuyến nghị là `simplified`, `pinyin`, `han_viet`, `meaning_vi`, `pos`, `hsk_level` và `mnemonic_vi`. Trình nhập nhận danh sách phẳng và JSON nhóm theo cấp. Dùng `--level` khi cần cấp mặc định hoặc `--meaning-field` để chỉ định trường nghĩa tiếng Việt. Có thể nhập lại để điền trường còn thiếu và giữ ID, các nguồn liên kết, lịch ôn và lịch sử.

```sh
docker compose cp hsk-1-5.csv backend:/tmp/hsk-1-5.csv
docker compose exec backend python -m app.seeds.cli /tmp/hsk-1-5.csv
```

Nếu chạy Python trực tiếp với `DATABASE_URL` trỏ tới cơ sở dữ liệu đã migrate, dùng `python scripts/import_hsk_data.py hsk-1-5.json`.

## Phát triển và kiểm thử

Cần Python 3.11 trở lên và Node.js 22. Tạo môi trường ảo rồi cài phụ thuộc bằng `python -m pip install -r backend/requirements-dev.txt`. Đặt `DATABASE_URL` tới PostgreSQL 16 đang chạy. Để thử cục bộ bằng SQLite, có thể dùng `sqlite:///./dev.db`. Cho các định dạng Office cũ khi chạy ngoài Docker, cài LibreOffice và đặt `soffice` hoặc `libreoffice` trên PATH.

```sh
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Trong terminal khác, từ thư mục gốc chạy `cd frontend`, `npm ci` và `npm run dev`. Vite chuyển tiếp đường dẫn `/api/` sang backend cổng 8000.

```sh
# Trong backend
python -m pytest

# Trong frontend
npm run typecheck
npm run build

# Từ thư mục gốc
docker compose config --quiet
```

Xem [AGENT.md](AGENT.md) để biết các quyết định kiến trúc và kết quả xác minh.
