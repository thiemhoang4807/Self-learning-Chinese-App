# Nhật ký triển khai

## Kiến trúc

- FastAPI, SQLAlchemy 2 và Alembic quản lý lược đồ PostgreSQL 16. Từ, mẫu câu và câu ví dụ dùng chung khóa chính qua các bảng liên kết nguồn. Thẻ và lịch sử ôn được lưu riêng theo loại mục và ID.
- Backend cập nhật lược đồ bằng Alembic khi container khởi động. Dữ liệu mẫu được nạp trong giao dịch với khóa PostgreSQL để hỗ trợ khởi động lặp lại.
- React 18 và Vite phục vụ qua Nginx. Nginx chuyển tiếp `/api/` sang backend cùng origin. Compose mặc định chỉ mở cổng web trên loopback cho ứng dụng cá nhân.
- Tiến độ dùng khung HSK 2.0 theo yêu cầu, với mục tiêu 2.500 từ cho HSK 1–5 và bài viết kiểu câu 99. Dữ liệu bổ sung đi qua trình nhập CSV hoặc JSON.

## Giai đoạn 1

- Clone `main` bằng `git clone --branch main https://github.com/thiemhoang4807/Self-learning-Chinese-App.git .` và giữ commit gốc `71241c3`.
- Cài môi trường bằng `python -m venv .venv`, sau đó `python -m pip install -r backend/requirements-dev.txt` trong môi trường ảo. `python -m pip check` trả về không có phụ thuộc lỗi.
- Tạo migration `0001` bằng `alembic revision --autogenerate --rev-id 0001 -m 'initial study schema'`. `alembic upgrade head` và `alembic check` đều qua trên SQLite và PostgreSQL 16.16.
- Hai lần khởi động API với PostgreSQL giữ nguyên 182 từ (169 từ thuộc HSK 1–5), 246 chữ, 350 liên kết chữ, 25 mẫu ngữ pháp với ví dụ và 18 cặp từ. `python scripts/import_hsk_data.py` đã nhập thử toàn bộ danh mục CTI trên SQLite và giữ nguyên trạng thái thẻ có sẵn.
- `npm install --no-audit --no-fund` tạo lockfile cho frontend. `docker compose config` trả mã 0 với Docker CLI cục bộ và Compose v2.40.3.
- Commit `feat: scaffold monorepo, database schema, and HSK seeds` trên `main`. Chờ các giai đoạn sau trước khi đẩy lên GitHub.

## Giai đoạn 2

- Đã nối 20 đường dẫn REST, gồm FSRS 6.3.3, hàng đợi ôn theo nguồn/cấp độ, nhập tài liệu theo hai luồng, câu i+1 có kiểm tra từ đã biết, chấm bài, trình đọc, cây chữ và tiến độ.
- Dịch vụ nạp dùng danh mục CTI để xác định cấp HSK. Xác nhận nạp chạy trong giao dịch và dùng cùng ID từ, mẫu câu và câu ví dụ khi nạp lại.
- `python -m compileall -q app` và sinh OpenAPI đã qua. `python -m pytest -q -o pythonpath=. .pytest_cache/test_phase2_services.py` chạy 7 kiểm tra dịch vụ AI/nạp với dữ liệu giả lập bên ngoài.
- Smoke test FastAPI với PostgreSQL 16.16 đã qua cho 7 lựa chọn chế độ ôn, gửi lại đánh giá không tạo lượt thứ hai, đọc văn bản, cây chữ, tiến độ, cặp từ, lấy 5 từ và trường hợp thiếu khóa Gemini. Gọi Edge TTS thật trả MP3 và lượt gọi sau lấy lại cùng nội dung và ETag từ cache.
- Commit `feat: implement study engine, ingestion, and HSK APIs` trên `main`. Chờ hoàn thành frontend và xác minh cuối.

## Giai đoạn 3

- Hoàn thành PWA React với năm khu vực chính, phím tắt, cài đặt Pinyin và giao diện sáng/tối, bảng duyệt nội dung nạp, cây chữ và danh sách phát rảnh tay.
- `npm run typecheck` và `npm run build` đều qua. `npm run preview` phục vụ đúng bản build và chuyển tiếp `/api/dashboard` tới FastAPI.
- Kiểm tra trên trình duyệt trên desktop và viewport 390 × 844. Đã mở buổi 8 thẻ, lật thẻ, mở cây chữ, ghi đánh giá và chuyển thẻ. Trình đọc tách đoạn mẫu, tra nghĩa và thêm từ vào kho. Chế độ nghe phát âm, hiện nghĩa rồi tự chuyển thẻ. Trang nạp báo lỗi bằng tiếng Việt khi thiếu khóa Gemini. Manifest và biểu tượng PWA được nạp từ bản build.
- Commit `feat: build Vietnamese Mandarin study PWA` trên `main`.

## Giai đoạn 4

- Sửa luồng giữ văn bản dán khi trích xuất thất bại và nối mẫu ngữ pháp vào câu đã nạp trước đó nếu câu chưa có mẫu. Cây chữ hiển thị thêm từ ghép trong danh mục CTI. Các mục đồng tự dùng chung một thẻ và được tính vào cấp tương ứng trong mục tiêu HSK.
- `python -m pytest -q` trong `backend` trả **16 passed** cùng 4 cảnh báo về API sắp ngừng hỗ trợ trong các thư viện phụ thuộc. Kiểm thử gồm FSRS, đánh dấu từ hay sai, nguồn trùng, tách từ, độ phủ, dự báo, đọc PDF/DOCX/XLSX/CSV và chấm bằng phản hồi Gemini mô phỏng.
- `npm run typecheck` và `npm run build` trong `frontend` đều trả mã 0. `node --check frontend/dist/sw.js` trả mã 0. `docker compose config` và `docker compose config --services` trả mã 0, với `postgres`, `backend`, `frontend`.
- `python -m app.seeds.cli` nhập 2.493 mục giản thể duy nhất từ 2.500 mục thi vào PostgreSQL 16, giữ lịch sử đánh giá hiện có. `python scripts/import_hsk_data.py --help` cũng chạy thành công.
- Kiểm thử Gemini thật cần khóa API. Docker CLI đã xác thực cấu hình. Kiểm thử khởi động container và chuyển đổi PowerPoint/Word cũ cần Docker Engine hoặc LibreOffice trong môi trường kiểm thử.
- Commit `test: verify study flows and document setup` trên `main`. Lệnh đẩy là `git push -u origin main` tới `https://github.com/thiemhoang4807/Self-learning-Chinese-App.git`.
