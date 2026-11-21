# Học Trung

Ứng dụng PWA tự học tiếng Trung cho người Việt. Bạn có thể ôn nhanh 8 thẻ, nghe rảnh tay, dán ảnh hoặc văn bản từ tài liệu, tra nghĩa trong đoạn đọc và luyện viết trên máy tính.

Ứng dụng dùng khung **HSK 2.0** theo yêu cầu, với mục tiêu 2.500 mục từ HSK 1–5 và bài viết kiểu câu 99. Chinese Testing International công bố triển khai HSK 3.0 từ ngày 13/12/2026. Bạn có thể đối chiếu thể thức và đề cương của kỳ thi mình đăng ký. [Thông báo của CTI](https://old.chinesetest.cn/gonewcontent.do?flag=kdnew&id=51336883)

## Chạy bằng Docker Compose

Cần Docker với Compose v2. Mở terminal ở thư mục gốc của dự án.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Trên macOS hoặc Linux, dùng `cp .env.example .env` cho bước sao chép. Khi dịch vụ sẵn sàng, mở [Học Trung trên máy này](http://localhost:8080). Trình duyệt có thể cài ứng dụng từ menu cài đặt PWA. Mặc định cổng web chỉ mở trên máy chạy Docker. Trình duyệt trên thiết bị khác cần địa chỉ HTTPS để cài PWA.

Sửa `GEMINI_API_KEY` trong `.env` để bật trích xuất tài liệu, tra nghĩa từ mới, tạo câu i+1 và chấm bài. `GEMINI_MODEL` mặc định là `gemini-2.5-flash`. Nếu tài khoản chưa có quyền dùng model này, đặt `GEMINI_MODEL=gemini-3.5-flash-lite`. Sau khi sửa biến môi trường, chạy `docker compose up -d backend`. [Lịch thay đổi model của Google](https://ai.google.dev/gemini-api/docs/deprecations#gemini-2.5-flash-models)

PostgreSQL và cache MP3 có volume riêng để giữ tiến độ khi dựng lại container. `docker compose logs -f backend` hiển thị tiến trình khởi động và lỗi. `docker compose down` dừng các dịch vụ và giữ dữ liệu.

## Sử dụng

1. Mở **Học hôm nay** và chọn **Học nhanh 2 phút**, một dạng bài, hoặc một buổi theo cấp độ và nguồn. Dùng `Space` để lật thẻ, `R` để nghe lại, `P` để hiện hoặc ẩn Pinyin và `1`–`4` để đánh giá mức nhớ. Khi cần nghe rảnh tay, chọn **Chế độ Học Lười**.
2. Ở **Nạp tài liệu**, thả một tệp hoặc nhấn `Ctrl+V` để trích xuất ảnh chụp hay văn bản đã sao chép. Sửa và chọn các mục trong bảng rồi bấm **Lưu vào kho ôn**. Mỗi lần lưu tạo một nguồn. Để ôn một trang chiếu riêng, nạp ảnh hoặc tệp của trang đó thành nguồn riêng.
3. Mở **Luyện HSK 4–5** để làm bài cặp từ, viết đoạn 5 từ hoặc đọc và tra từ trực tiếp. Bấm vào một chữ Hán để xem bộ thủ, chiết tự và các từ HSK chứa chữ đó.
4. Xem độ phủ, dự báo và các từ hay sai trong **Tiến độ HSK**. Dự báo dùng số từ lần đầu được đánh giá từ mức **Nhớ được** trong 7 ngày gần nhất. Cài đặt Pinyin và giao diện được lưu trên trình duyệt.

Định dạng nạp gồm PNG, JPG, WebP, PDF, PPTX/PPT, DOCX/DOC, XLSX, CSV và TXT. Giới hạn mặc định là 25 MiB mỗi tệp và 24 trang cho luồng ảnh. Nội dung cần trích xuất hoặc chấm được gửi cho Gemini. Edge TTS nhận văn bản tiếng Trung cần đọc, trả MP3 và ứng dụng lưu bản phát tại chỗ. Bản cài PWA giữ giao diện trong cache. Các thao tác học và đồng bộ tiến độ cần kết nối tới backend.

## Bổ sung từ vựng HSK

Dữ liệu mẫu có 182 từ, gồm 169 từ thuộc HSK 1–5, 246 chữ Hán, 25 mẫu ngữ pháp kèm câu ví dụ và 18 cặp từ dễ nhầm. Cây chữ bổ sung các mục từ liên quan từ danh mục chuẩn khi bạn mở một chữ. Các mục nhập chỉ có chữ Hán có thể được tra thêm nghĩa tiếng Việt trong Trình đọc. Từ trùng chữ giản thể dùng chung thẻ và lịch ôn. [Danh mục HSK 2.0 của CTI](https://old.chinesetest.cn/userfiles/file/HSK/HSK-2015.xlsx)

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
