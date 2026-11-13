# Benchmark — 30 câu hỏi

[questions.json](questions.json) chứa 30 câu hỏi tiếng Anh (cùng ngôn ngữ với corpus): **22 dev / 8 test**, 20 câu từ FM 7-22, 6 câu từ HHS, 4 câu từ WHO. Bộ câu hỏi được chốt **trước khi** chạy bất kỳ thí nghiệm chunk/embedding nào.

## Định dạng

Mỗi câu có `id`, `split`, `type`, `question`, `expected_answer`, `gold_source_id`, `gold_page`, `evidence_quote`.

- `gold_page` là số trang vật lý của PDF (bắt đầu từ 1), cùng hệ với `page` trong [data/manifest.json](../data/manifest.json).
- `alt_gold` (nếu có) liệt kê các trang khác cũng trả lời được câu hỏi, mỗi trang có `evidence_quote` riêng. Truy xuất trúng bất kỳ trang nào trong số này đều được tính.
- `filter` (nếu có) là bộ lọc metadata của câu hỏi.
- `type`: `direct` (14), `paraphrase` (5), `conditional` (3), `table` (1), `metadata` (7).

## Định nghĩa hit

Một chunk là hit khi nó thuộc đúng `(source, page)` của gold hoặc `alt_gold` **và** chứa trọn `evidence_quote` của trang đó. So khớp phân biệt hoa thường, sau khi gộp khoảng trắng.

Evidence được chép nguyên văn từ text đã chuẩn hóa, giữ cả lỗi tách từ của pypdf (ví dụ `maxima l`, `trave ling`, `50 –100`), vì chunk cũng mang đúng các lỗi đó.

Trang chỉ chứa một phần bằng chứng không được ghi là gold. Ví dụ q26: HHS p36 và p56 chỉ nêu một phần lợi ích, chỉ p20 liệt kê đủ.

## Chia dev / test

- Test gồm q16–q20 và q28–q30.
- Không trang gold nào của test trùng trang gold của dev (script kiểm tra điều này).
- Với FM 7-22, các chương của test (5, 11, 12) không có câu dev nào.

Nguy cơ rò rỉ còn lại:

- HHS chương 5 có ở cả hai tập: q12 (dev) có trang thay thế p71, q19 (test) dùng p68–p69.
- Phần tóm tắt của WHO có trang liền kề ở hai tập: p10–p11 (dev) và p12, p14 (test).
- WHO lặp cùng một khuyến nghị cho nhiều nhóm đối tượng, nên câu dev và câu test có thể kéo về các đoạn rất giống nhau.

## Câu có filter

7 câu: q09, q13, q14, q24 (dev) và q18, q20, q30 (test).

- Giá trị filter là phạm vi mà người hỏi nêu ngay trong câu hỏi: tên chương (`section`) hoặc tổ chức ban hành (`publisher`). Đây là **input giả định được cung cấp trước khi truy xuất**, không lấy từ nhãn gold.
- Cấu hình A và B không dùng filter. Cấu hình C chỉ áp filter cho 7 câu này; 23 câu còn lại chạy giống B.
- Các câu này được chọn ở chỗ nhiều nguồn nói về cùng chủ đề. Ví dụ q24: chương 14 ghi tối đa 1½ quart nước mỗi giờ, còn chương 8 ghi 1 quart.

## Kiểm chứng

```bash
cd starter && .venv/bin/python -m scripts.verify_benchmark
```

Script báo lỗi nếu: evidence không nằm nguyên văn trên trang gold, trang gold không phải trang nội dung, filter loại chính trang gold của nó, giá trị filter không có trong corpus, dev và test dùng chung trang gold, hoặc thiếu số lượng tối thiểu (20 câu, 15 dev, 5 test, 3 câu filter trong đó 1 câu test). Script cũng cảnh báo khi evidence chính xuất hiện nguyên văn ở trang chưa được liệt kê.

- Kiểm chứng tự động: đạt (30/30 câu, không cảnh báo).
- [ ] Học viên đọc lại từng câu, đáp án và evidence trên PDF gốc.

Bộ câu hỏi được soạn nháp với trợ giúp của AI (Claude Code), evidence trích bằng script từ text đã chuẩn hóa.

## Tiêu chí chọn cấu hình (chốt trước khi xem test)

Chọn trên **dev**, theo thứ tự ưu tiên:

1. Evidence Hit@3 cao hơn.
2. Nếu bằng nhau: Hit@1 cao hơn.
3. Nếu vẫn bằng: điểm coherence trung bình cao hơn.
4. Nếu vẫn bằng: ít chunk và thời gian ingest ngắn hơn.

Test chỉ chạy một lần sau khi đã cố định cấu hình, không dùng để chỉnh.

## Mẫu chấm tay (chốt trước khi chạy test)

- **Coherence:** 10 trang nội dung cách đều nhau theo thứ tự corpus (cứ 34 trang lấy một, bắt đầu từ trang thứ 18), lấy ký tự giữa trang. Mỗi chunking (A, B) chấm chunk chứa vị trí đó; C dùng chung chunk với B. Bảng chấm: [results/audit/coherence.json](../results/audit/coherence.json).
- **Metadata và grounding:** 5 câu test đầu theo ID (q16–q20), cùng 5 câu cho cả ba cấu hình. Bảng chấm được tạo từ trace test và không hiển thị cờ hit, để nhãn tay độc lập với điểm tự động.
- **Tuân thủ filter:** tính tự động trên toàn bộ câu có filter của từng tập (dev 4 câu, test 3 câu).
