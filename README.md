# AERO — Escape Run

Ứng dụng cục bộ để dùng Grove MMA7660 trên Arduino UNO R4 WiFi làm tay lái máy bay 2D. Chạy trên macOS hoặc Linux với Python 3.9+; không cần cài thư viện, npm hay dịch vụ mạng. Không nạp lại firmware và không gửi lệnh tới board.

## Chơi Escape Run

Hiệu chỉnh sensor, nhập tên phi công rồi bấm **Bắt đầu · 60 giây**. Giữ tay cân bằng trong lúc đếm ngược. Máy bay tự tiến; nghiêng sensor để bay trái/phải hoặc lên/xuống, tránh các vật cản màu cam. Chỉ cần bay vào khoảng trống, không có khe nghiêng hay điều kiện khớp góc cánh.

- Lượt chơi 60 giây, 3 giáp. Hết giáp sẽ kết thúc sớm. Về đích được thưởng 200 điểm cho mỗi giáp còn lại.
- Ba đợt đầu chỉ có một vật cản, cách nhau hơn 4 giây. Về sau xen kẽ hai vật cản hoặc vật cản dịch chuyển chậm, luôn để lại đường tránh rộng.
- Vật cản lớn dần khi tới gần. Vòng nét đứt đánh dấu vị trí của vật cản tiếp theo; có thời gian báo trước để đổi hướng.
- Vùng va chạm nhỏ quanh thân máy bay để dễ né; góc chao cánh không tham gia điều kiện va chạm. Mỗi đợt được kiểm tra khi tới độ sâu của máy bay và chỉ gây tối đa một lần mất giáp.
- Né một đợt được 100 điểm, né sát được thêm 75 điểm. Combo tăng hệ số điểm mỗi 3 đợt, tối đa ×5; va chạm mất 1 giáp và xóa combo.
- Có âm báo, hạt sáng và lóe đỏ khi né hoặc va chạm. Có nút tắt âm thanh.
- **Space** hoặc nút **Tạm dừng** để dừng; tiếp tục có đếm ngược 3 giây. Mất dữ liệu USB, hiệu chỉnh lại hoặc đổi tab sẽ tự tạm dừng.
- Kết quả có điểm, số đợt né thành công, combo cao nhất và số pha né sát. **Lưu điểm** ghi top 5 trên trình duyệt này. Bảng điểm riêng cho chế độ né vật cản; điểm từ chế độ khe nghiêng cũ được giữ riêng. Demo không được ghi bảng xếp hạng.

Trước khi bắt đầu vẫn có thể nghiêng để tập điều khiển. Giới hạn chao cánh hiện tại **±90°**, chúi/ngửa **±20°**. Khi đang trong lượt, nút đưa máy bay về giữa bị khóa. Có thể chỉnh độ nhạy và đảo trục theo tư thế cầm.

## Chạy

Từ thư mục chứa `server.py`, chạy:

```sh
python3 server.py
```

Yêu cầu: Python 3.9+ trên macOS hoặc Linux, trình duyệt có Canvas và EventSource. Không cần cài Python package hay chạy `npm install`. Node.js 18+ chỉ cần khi chạy kiểm tra thuật toán.

Mở **http://127.0.0.1:8765** trong trình duyệt. Trên Mac có thể chạy `Start Motion Lab.command`. Giữ cửa sổ Terminal mở; nhấn Ctrl+C để dừng. Nếu cổng 8765 đang bận, dùng `python3 server.py --port 8766` rồi mở địa chỉ tương ứng.

Sensor phải cắm vào một cổng **I²C** của Grove shield. Arduino nối USB với Mac. Đóng Serial Monitor của Arduino IDE hoặc chương trình khác đang giữ cổng USB trước khi chạy.

Repo chứa ứng dụng trên máy tính; firmware Arduino hiện có trên board không nằm trong repo. Để dùng board khác, cần firmware xuất JSON qua serial theo định dạng bên dưới. Có thể bấm **Thử demo** để thử giao diện và game mà không cần board hoặc sensor.

## Cách dùng

1. Ứng dụng tự tìm cổng USB. Nếu có nhiều board, chọn đúng cổng trong danh sách. Bấm ↻ để làm mới danh sách.
2. Cầm sensor theo tư thế tự nhiên, giữ yên rồi bấm **Đặt tư thế cân bằng**. Đợi 1,8 giây; hiệu chỉnh sẽ từ chối nếu thiếu mẫu hoặc chuyển động quá nhiều.
3. Nghiêng trái/phải để lượn và di chuyển ngang. Chúi/ngửa để đi xuống/lên. Nghiêng nhẹ cho phản ứng nhỏ, nghiêng thêm để tăng tốc dần. Trả về điểm cân bằng để giảm tốc và dừng. Máy bay dừng ở biên màn hình.
4. Nếu hướng chưa đúng với cách cầm, dùng **Đảo trái / phải**, **Đảo lên / xuống**, **Đổi trục X / Y**. Điểm giữa được tính tương đối theo tư thế hiệu chỉnh, kể cả khi cầm nghiêng hoặc úp module.
5. Tăng độ nhạy để nghiêng ít hơn; tăng vùng cân bằng để giảm rung tay; tăng độ mượt để lọc mạnh hơn (đồng thời tăng độ trễ).
6. **Đưa máy bay về giữa** đặt lại vị trí mô phỏng. Hiệu chỉnh lại nếu đổi cách cầm sensor.

**Thử demo** giải phóng USB và tạo dữ liệu mô phỏng, có nhãn DEMO rõ ràng. Bấm hiệu chỉnh trong demo để bắt đầu bay. Bấm **Về USB** để trở lại thiết bị thật, rồi hiệu chỉnh lại. Các cài đặt độ nhạy được lưu trong trình duyệt; điểm cân bằng được đặt lại khi đổi nguồn hoặc tải lại trang.

## Dữ liệu và giới hạn

Backend đọc JSON từng dòng ở 115200 baud từ firmware `wifi-diag-3` hiện có:

```json
{"t":"f","seq":1391,"ms":1149814,"ax":750,"ay":375,"az":609}
{"t":"i","acc":"MMA7660","fw":"wifi-diag-3","fps":40}
```

`ax`, `ay`, `az` giữ nguyên đơn vị firmware trên biểu đồ. Góc nghiêng dùng hướng của vector gia tốc đã lọc, nên không cần giả định hệ số đổi đơn vị. Tốc độ mẫu hiển thị là số frame USB thực tế nhận được, không lấy trường `fps` của firmware. Giao diện dựng hình bằng `requestAnimationFrame`, nội suy tư thế máy bay và truyền trạng thái qua Server-Sent Events.

Bộ điều khiển analog lọc góc nghiêng liên tục ở từng khung hình, thay vì chỉ thay đổi khi có mẫu USB mới. Vùng cân bằng tròn mặc định 2° và đường đáp ứng mềm cho phép điều khiển chéo và chỉnh hướng nhỏ. Tốc độ tăng/giảm dần, góc nghiêng máy bay dùng mô hình lò xo có giảm chấn. Bản này đặt lại các thông số cũ một lần để áp dụng mặc định mới; hiệu chỉnh lại sau khi tải lại trang.

Luồng USB firmware hiện tại đo được khoảng **5 mẫu/giây**, dù trường `fps` là 40. Nội suy làm chuyển động liền hơn nhưng không tạo thêm thông tin sensor hoặc loại bỏ độ trễ lấy mẫu 200 ms. Bản này chỉ thay đổi phần mềm trên Mac; muốn phản hồi nhanh hơn nữa cần điều chỉnh tốc độ xuất USB trong firmware.

Vị trí máy bay là **mô phỏng bằng tốc độ điều khiển từ độ nghiêng**, không phải vị trí vật lý của sensor. Không tích phân gia tốc để đo quãng đường. Cảm biến gia tốc không đo được yaw; vung tay hoặc gia tốc mạnh có thể làm sai góc nghiêng tạm thời. Thiết kế dành cho nghiêng tay vừa phải, khoảng ±30°.

Nếu không nhận frame gia tốc mới trong 2 giây, hoặc mất kết nối server, lệnh điều khiển về 0 và máy bay dừng. Backend tự thử nối lại USB sau khi rút/cắm lại. Cổng HTTP chỉ lắng nghe trên máy này (`127.0.0.1`).

## Cấu trúc

- `server.py`: cầu nối USB, trạng thái kết nối, HTTP và SSE; chỉ dùng thư viện chuẩn Python.
- `web/index.html`, `web/style.css`: giao diện responsive.
- `web/app.mjs`: kết nối, hiệu chỉnh, đồ thị và vẽ máy bay bằng Canvas 2D.
- `web/control.mjs`: phép tính hướng trọng lực, bộ lọc, góc nghiêng và vùng cân bằng.
- `web/game.mjs`: lịch vật cản, kiểm tra va chạm, tính điểm, giáp và trạng thái lượt chơi.
- `web/game-view.mjs`: vẽ đường bay, vật cản, máy bay, hiệu ứng và âm báo.
- `tests/`: kiểm tra thuật toán và luồng đọc serial qua pseudo-terminal.

## Kiểm tra

```sh
python3 -m unittest discover -s tests -v
node --test tests/control.test.mjs tests/game.test.mjs
```

Để mở giao diện mà không tự giữ cổng USB: `python3 server.py --no-auto`. Có thể chỉ định cổng thủ công: `python3 server.py --serial /dev/cu.usbmodemXXXX` (thay bằng cổng của board).

## Lệnh tiện dụng và đóng gói

```sh
make run      # Chạy server cục bộ
make test     # Chạy kiểm tra Python và JavaScript
make package  # Tạo dist/aero-escape-run.zip từ commit hiện tại
```

ZIP chứa mã nguồn, hướng dẫn chạy và bộ kiểm tra; không chứa thư mục `.git`, Python cache, môi trường ảo hay file log. Người nhận giải nén rồi chạy `python3 server.py` từ thư mục `aero-escape-run`. Commit các thay đổi cần phát hành trước khi chạy `make package`.
