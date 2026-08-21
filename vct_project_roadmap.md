# Lộ Trình Phát Triển Dự Án: VCT Esports Analytics & Match Predictor

Tài liệu này mô tả chi tiết kiến trúc và lộ trình 6 bước để xây dựng dự án phân tích và dự đoán kết quả giải đấu Valorant (VCT), được thiết kế tối ưu cho vị trí **Software Engineer Intern**.

## Tổng quan Kiến trúc Hệ thống (Tech Stack)

Kiến trúc Microservices chia tách rõ ràng các tầng (layers):

*   **Database (Cơ sở dữ liệu):** PostgreSQL (Lưu trữ lịch sử trận đấu, thông tin đội tuyển, tuyển thủ).
*   **Data Processing Core (Lõi xử lý):** **C++** (Đảm nhiệm tính toán các chỉ số thống kê cường độ cao, được nhúng vào Python qua thư viện `pybind11`).
*   **Machine Learning:** Python (Sử dụng `XGBoost` hoặc `Random Forest` để dự đoán).
*   **Backend:** Python + **FastAPI** (Xây dựng RESTful API giao tiếp nhanh, hỗ trợ xử lý bất đồng bộ).
*   **Frontend:** **Streamlit** (Tạo Web Dashboard trực quan, gọi dữ liệu từ API).
*   **DevOps / CI-CD:** Docker, GitHub Actions, Render/Railway (Triển khai ứng dụng).

---

## Lộ trình thi công chi tiết (6 Bước)

### Bước 1: Thiết kế Cơ sở dữ liệu và Thu thập Dữ liệu (Tuần 1-2)
*   **Thiết kế Database Schema:** Lên cấu trúc các bảng trong PostgreSQL:
    *   `Teams`: ID, Name, Region.
    *   `Players`: ID, Team_ID, Name, Role.
    *   `Matches`: Match_ID, Team_A, Team_B, Map, Score_A, Score_B, Date.
    *   `Player_Stats`: Match_ID, Player_ID, Kills, Deaths, Assists, ACS.
*   **Viết Script Cào dữ liệu:** Sử dụng Python (`BeautifulSoup` hoặc `Selenium`) cào dữ liệu từ trang VLR.gg. 
*   **Lưu trữ:** Đổ dữ liệu thô vào PostgreSQL thông qua thư viện `SQLAlchemy`.

### Bước 2: Xây dựng Lõi Xử lý Hiệu năng cao (Tuần 3)
*   **Viết Logic bằng C++:** Xây dựng các hàm thuật toán tính toán phong độ của tuyển thủ (dựa trên lịch sử đối đầu, KDA, ACS) trong khoảng thời gian `O(N log N)` hoặc tối ưu hơn.
*   **Tích hợp `pybind11`:** Đóng gói đoạn code C++ này thành một module (file `.so` hoặc `.pyd`) để Python có thể `import` trực tiếp.

### Bước 3: Huấn luyện Mô hình AI Dự đoán (Tuần 4)
*   **Tiền xử lý (Feature Engineering):** Rút trích các đặc trưng (features) từ Database (như: tỉ lệ thắng Map Bind của Đội A, phong độ 5 trận gần nhất của Đội B).
*   **Huấn luyện:** Đưa dữ liệu vào mô hình `XGBoost`. Phân chia tập Train/Test để kiểm tra độ chính xác (Accuracy, F1-Score).
*   **Đóng gói Model:** Sau khi train xong, xuất mô hình ra file dạng `model.pkl` (pickle) hoặc `ONNX` để backend gọi ra sử dụng.

### Bước 4: Xây dựng Backend API (Tuần 5)
*   **Thiết lập FastAPI:** Khởi tạo server bằng Python.
*   **Viết các Endpoints:**
    *   `GET /teams/{team_id}`: Trả về thông tin và chỉ số của đội.
    *   `GET /matches/history`: Trả về lịch sử đối đầu.
    *   `POST /predict`: Nhận đầu vào là 2 đội tuyển cùng tên Map, gọi Lõi C++ tính toán, đưa vào model AI, và trả về kết quả JSON.

### Bước 5: Xây dựng Giao diện Web (Tuần 6)
*   **Khởi tạo Streamlit:** Dựng một giao diện gồm thanh Sidebar chọn tham số dự đoán.
*   **Kết nối API:** Frontend gửi request tới `POST /predict` của Backend.
*   **Trực quan hóa:** Hiển thị thanh tiến trình tỉ lệ thắng và vẽ biểu đồ Radar so sánh các chỉ số bằng `Plotly`.

### Bước 6: Đóng gói và Vận hành - CI/CD (Tuần 7)
*   **Docker hóa:** Viết `Dockerfile` để đóng gói Frontend, Backend và Database thành các container độc lập (sử dụng `docker-compose`).
*   **CI/CD Pipeline:** Viết cấu hình `.github/workflows/main.yml` cho GitHub Actions (tự động test, build docker image).
*   **Triển khai (Deploy):** Đưa Database lên nền tảng đám mây, Backend và Frontend lên dịch vụ hosting để lấy link URL gắn vào CV.
