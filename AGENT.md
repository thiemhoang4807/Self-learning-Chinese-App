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
