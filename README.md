# Story2Video

**Story2Video** là một ứng dụng web mã nguồn mở mãnh mẽ, cho phép bạn chuyển đổi văn bản hoặc các câu chuyện thành video chuyên nghiệp với phụ đề tự động. Dự án được phát triển với tiêu chí **hoàn toàn miễn phí** và dễ dàng sử dụng.

## 🌟 Điểm nổi bật

- 💸 **Hoàn toàn miễn phí:** Sử dụng Edge TTS để tạo giọng đọc chất lượng cao mà không tốn phí bản quyền.
- 🎙️ **Giọng đọc AI đa dạng:** Hỗ trợ hàng trăm giọng đọc từ Edge TTS (Microsoft), bao gồm các giọng đọc tiếng Việt truyền cảm (Hoài My, Nam Minh).
- 🎬 **Render video trực tiếp:** Video được xử lý ngay trên trình duyệt của bạn (Client-side rendering), đảm bảo quyền riêng tư và tốc độ nhanh chóng.
- 🖼️ **Tùy chỉnh linh hoạt:** Thay đổi hình nền, màu sắc, font chữ, kích thước video (YouTube, TikTok, Square).
- 📝 **Xuất phụ đề:** Hỗ trợ xuất file phụ đề định dạng SRT, VTT và JSON.

## 🚀 Hướng dẫn cài đặt

Dự án yêu cầu cài đặt [Python](https://www.python.org/).

1. **Clone repository:**
   ```bash
   git clone https://github.com/dvchd/story2video.git
   cd story2video
   ```

2. **Cài đặt các thư viện cần thiết:**
   ```bash
   pip install fastapi uvicorn edge-tts python-dotenv
   ```

3. **Chạy ứng dụng:**
   ```bash
   python main.py
   ```

4. **Trải nghiệm:**
   Mở trình duyệt và truy cập: `http://localhost:8001`

## 🐳 Triển khai với Docker

Bạn có thể dễ dàng triển khai dự án bằng Docker:

1. **Sử dụng Docker Compose:**
   ```bash
   docker-compose up -d --build
   ```

2. **Cấu hình trên Coolify:**
   - Chọn nguồn từ GitHub repository.
   - Coolify sẽ tự động nhận diện `Dockerfile` hoặc bạn có thể cấu hình sử dụng `docker-compose.yml`.
   - Đảm bảo port `8001` được expose.

## ️ Công nghệ sử dụng

- **Backend:** FastAPI, Edge TTS.
- **Frontend:** HTML5 Canvas, Web Audio API, MediaRecorder API (xử lý video trực tiếp trên trình duyệt).
- **Subtitles:** Tự động tạo và đồng bộ hóa phụ đề theo giọng đọc.

## 📄 License

Dự án này được phát hành dưới bản quyền **MIT License**. Bạn có thể tự do sử dụng, chỉnh sửa và phân phối.

---
*Phát triển bởi cộng đồng - Vì mục tiêu chia sẻ kiến thức và công cụ miễn phí.*
