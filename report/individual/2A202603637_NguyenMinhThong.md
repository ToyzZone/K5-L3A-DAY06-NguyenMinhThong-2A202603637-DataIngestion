# Báo cáo cá nhân — Day 6

**Học viên:** Nguyễn Minh Thông · **MSSV:** 2A202603637 · **Lớp:** L3A

## Dữ liệu và pipeline

**Chủ đề, nguồn, quyền, số trang.** Corpus về thể lực và hoạt động thể chất, gồm ba tài liệu tiếng Anh công khai:

| Nguồn | Quyền sử dụng | Trang vật lý | Trang nội dung | Ký tự |
|---|---|---:|---:|---:|
| FM 7-22 Holistic Health and Fitness (Lục quân Mỹ, 2020) | "Approved for public release; distribution is unlimited" (trang bìa) | 244 | 192 | 568.048 |
| Physical Activity Guidelines for Americans, 2nd ed. (HHS, 2018) | Tác phẩm của chính phủ liên bang Mỹ, thuộc phạm vi công cộng (17 U.S.C. 105) | 118 | 83 | 206.663 |
| WHO guidelines on physical activity and sedentary behaviour (WHO, 2020) | CC BY-NC-SA 3.0 IGO (ghi ở trang 4) | 104 | 67 | 246.641 |
| **Tổng** | | 466 | **342** | 1.021.352 |

Quy tắc tính: một trang nội dung là một trang vật lý của PDF nằm trong các chương nội dung đã liệt kê, không phải trang trùng lặp, và còn ít nhất 300 ký tự sau chuẩn hóa. Bìa, mục lục, bảng thuật ngữ, tài liệu tham khảo và phụ lục không được tính. Danh sách từng trang, số ký tự và lý do loại 124 trang còn lại nằm trong [data/manifest.json](../../data/manifest.json).

**Chuẩn hóa, lỗi và giới hạn.** Text được trích bằng pypdf 6.21.4, chuẩn hóa Unicode NFKC, đổi các ký tự bullet của font ký hiệu thành "•", gộp khoảng trắng và giữ nguyên ngắt dòng. Tiêu đề và chân trang lặp lại được xóa bằng regex, chỉ áp dụng cho hai dòng đầu và hai dòng cuối mỗi trang. Sáu trang gấp của WHO (13, 15, 17, 19, 21, 23) gần trùng trang liền kề nên bị loại để không nhân bản nội dung. Giới hạn còn lại:

- pypdf chèn khoảng trắng giữa từ ở một số chỗ (ví dụ "maxima l", "trave ling"); không sửa vì không có cách sửa an toàn.
- Một vài trang tóm tắt của WHO còn sót chữ chân trang sau khi làm sạch.
- pypdf cảnh báo thiếu fontTools khi đọc một số font; chưa đánh giá ảnh hưởng.

**Embedding, vector store, chi phí.**

- Model `BAAI/bge-small-en-v1.5` chạy local qua sentence-transformers 5.7.0 (torch 2.15.0, thiết bị MPS của Apple Silicon), ghim revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. Vector 384 chiều, đã chuẩn hóa độ dài, giới hạn 512 token.
- Query được thêm tiền tố "Represent this sentence for searching relevant passages: " theo hướng dẫn của model; document không thêm gì. Cả ba cấu hình dùng chung cách xử lý này.
- PostgreSQL 16.16 + pgvector 0.8.7 chạy bằng Docker Compose, một bảng `chunks`, khoảng cách cosine (`<=>`), quét tuần tự chính xác (không dùng index xấp xỉ).
- Chi phí 0 USD: không gọi dịch vụ trả phí.
- Lệnh chạy nằm ở cuối [README.md](../../README.md).

**Metadata.** Mỗi chunk lưu `document_id`, `source` (đường dẫn file PDF), `page` (số trang vật lý, đếm từ 1) và `char_start`/`char_end` (vị trí trong text của trang) để truy vết. Ba trường lọc bổ sung:

| Trường | Kiểu | Nguồn giá trị | Lý do |
|---|---|---|---|
| `publisher` | text | Tổ chức ban hành ghi trên tài liệu (US Army, HHS, WHO) | Ba tài liệu cùng nói về một chủ đề nhưng khuyến nghị khác nhau |
| `section` | text | Tên chương theo mục lục, gán theo khoảng trang trong [starter/data/sources.json](../../starter/data/sources.json) | Trong FM 7-22, hai chương có thể đưa con số khác nhau cho cùng một câu hỏi |
| `year` | int | Năm xuất bản ghi trên tài liệu | Truy vết phiên bản; không dùng để lọc trong benchmark |

## Cấu hình và benchmark

| | Chunking | Tham số | Truy xuất |
|---|---|---|---|
| A | Cửa sổ ký tự cố định | 500 ký tự, overlap 50 | Không lọc |
| B | Theo đoạn/heading: gói các đoạn liền nhau tới giới hạn; đoạn dài hơn thì cắt theo câu | Tối đa 800 ký tự, không overlap | Không lọc |
| C | Giống B, dùng chung index của B | Như B | Lọc theo `publisher` hoặc `section`, chỉ ở câu hỏi có filter |

- **Khác biệt duy nhất B–C** là bước lọc: cùng chunk, cùng vector, cùng bảng.
- **Giới hạn 800 của B** là mức tròn nhỏ nhất để ít nhất 90% đoạn của mỗi tài liệu không bị cắt (phân vị 90 của độ dài đoạn: FM 781, HHS 616, WHO 711). Mức này chọn từ thống kê độ dài, trước khi chạy truy xuất.
- **Tách đoạn** dựa trên hình dạng dòng (số thứ tự đoạn của FM, bullet, chú thích bảng, dòng ngắn kết thúc câu, dòng tiêu đề), vì lớp text của PDF không có dòng trống giữa các đoạn.

**Benchmark.** 30 câu hỏi tiếng Anh, chia 22 dev / 8 test trước khi chạy thí nghiệm (commit `652459e`). Có 7 câu filter (4 dev, 3 test); giá trị filter là phạm vi người hỏi nêu ngay trong câu, không lấy từ nhãn gold. Mỗi câu có đáp án, trang gold, evidence nguyên văn và các trang thay thế hợp lệ. Script [verify_benchmark.py](../../starter/scripts/verify_benchmark.py) kiểm tra evidence nằm nguyên văn trên trang gold và hai tập không dùng chung trang gold; kết quả 30/30 đạt. Chi tiết trong [benchmark/README.md](../../benchmark/README.md).

**Tiêu chí chọn, chốt trước khi xem test:** chọn trên dev theo Evidence Hit@3, rồi Hit@1, rồi coherence trung bình, rồi số chunk và thời gian ingest. Cấu hình được khóa ở commit `af25567`; test chạy một lần sau đó.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ingest (embed + lưu) | Chi phí |
|---|---|---:|---:|---:|---|---:|
| A | dev | 12/22 | 17/22 | 2.407 | 44,0 s + 1,4 s | 0 |
| A | test | 3/8 | 5/8 | 2.407 | 40,1 s + 1,2 s | 0 |
| B | dev | 15/22 | 20/22 | 1.805 | 38,5 s + 1,5 s | 0 |
| B | test | 3/8 | 7/8 | 1.805 | 35,4 s + 0,7 s | 0 |
| C | dev | 16/22 | 21/22 | 1.805 (index của B) | Không ingest thêm | 0 |
| C | test | 4/8 | 7/8 | 1.805 (index của B) | Không ingest thêm | 0 |

Độ dài chunk: A trung bình 467 ký tự (trung vị 500), tổng 235.456 token; B trung bình 565 ký tự (trung vị 622), tổng 210.619 token. Không chunk nào vượt 512 token. B có 74 chunk dưới 100 ký tự, A có 33.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,0 (n=10) | 15/15 | dev 1/4, test 2/3 | 0 / 1 / 4 câu, trung bình 1,8 |
| B | 1,9 (n=10) | 15/15 | dev 0/4, test 2/3 | 0 / 0 / 5 câu, trung bình 2,0 |
| C | 1,9 (n=10, cùng chunk với B) | 15/15 | dev 4/4, test 3/3 | 0 / 0 / 5 câu, trung bình 2,0 |

Phân bố điểm coherence: A có 10 chunk điểm 1; B có 9 chunk điểm 2 và 1 chunk điểm 1. Không chunk nào điểm 0.

"Filter tuân thủ" được tính tự động: số câu có cả ba kết quả top-3 nằm trong phạm vi câu hỏi yêu cầu, trên tổng số câu có filter của tập đó.

**Đường dẫn và cách chọn mẫu.**

- Trace top-3 và chỉ số: thư mục `results/dev/` và `results/test/` (mỗi cấu hình một file `traces_*.json`, kèm `summary.json`).
- Coherence: [results/audit/coherence.json](../../results/audit/coherence.json), 10 trang cách đều theo thứ tự corpus, lấy chunk chứa ký tự giữa trang. Vị trí được chốt trước khi có điểm truy xuất. Nhãn và lý do do Claude Code đề xuất theo thang 0–2 của GUIDE.md; học viên tự chấm lại từng ca và đồng ý với cả 20 nhãn.
- Metadata và grounding: [results/audit/metadata.json](../../results/audit/metadata.json) và [results/audit/grounding.json](../../results/audit/grounding.json), 5 câu test đầu theo ID (q16–q20). Quy tắc này được ghi vào repo trước khi chạy test; bảng chấm không hiển thị cờ hit. Nhãn do Claude Code đề xuất; học viên tự chấm lại từng ca và đồng ý với toàn bộ.
- Cách kiểm tra metadata: 45 bản ghi top-3 (15 mỗi cấu hình) ứng với 30 chunk khác nhau. Với mỗi chunk, đối chiếu trên PDF gốc ba việc: text có nằm trên đúng trang vật lý của đúng file; `section` có khớp tiêu đề in trên trang; `publisher` và `year` có khớp trang bìa hoặc trang bản quyền.
- Cách chấm grounding: xét cả top-3 của mỗi câu theo thang 0–2 của GUIDE.md. Top-3 của C giống hệt B ở cả 5 câu nên nhận cùng nhãn.
- Đối chiếu tự động (không thay cho chấm tay): cả 50 chunk khác nhau trong trace test đều có text nằm trên đúng trang vật lý của đúng file PDF; `section`, `publisher`, `year` khớp với sources.json.
- Trang diễn giải có tương tác: [lab_walkthrough.html](../lab_walkthrough.html), một file HTML, tải về rồi mở bằng trình duyệt. Trang đi lại bài làm theo thứ tự đã diễn ra và cho xem từng câu trong 30 câu hỏi: đáp án, bằng chứng, vị trí A và B cắt trang gold, nguyên văn top-3 của A, B, C. Dữ liệu trên trang lấy từ chính các file nêu ở trên, không có số liệu mới.

**Nạp lại.** Chunk ID ổn định theo tài liệu, trang, chiến lược và thứ tự. Mỗi lần nạp ghi đè ID đã có và xóa ID không còn trong phiên bản mới, trong một transaction. Pipeline nạp hai lần liên tiếp trong mỗi lần chạy và dừng nếu số dòng thay đổi. Qua ba lần chạy đầy đủ, số dòng giữ nguyên (A 2.407, B 1.805) và trace dev của hai lần chạy giống nhau từng byte.

## Phân tích và kết luận

**So sánh A–B (thay chunking).**

- B cao hơn A ở Evidence Hit@3 trên cả dev (20/22 so với 17/22) và test (7/8 so với 5/8).
- Nguyên nhân chính là A cắt ngang evidence. Ở dev, 4 trong 5 câu trượt của A (q04, q07, q11, q13) không có chunk nào chứa trọn evidence; ở test là q30. Với B, mọi câu đều có ít nhất một chunk chứa trọn evidence.
- B không tốt hơn ở mọi câu: A xếp đúng chunk lên hạng 1 trong khi B xếp hạng 2 hoặc 3 ở q02, q09, q10, q27 (dev) và q20 (test).
- Coherence của B cao hơn rõ: 1,9/2 so với 1,0/2. Cả 10 chunk của A đều kết thúc giữa từ hoặc giữa câu, và 9 trong 10 bắt đầu như vậy; không chunk nào nhận 0 vì câu chứa vị trí lấy mẫu vẫn nguyên. B mất điểm ở vị trí 6 (FM 7-22 trang 214): bảng chú giải từ viết tắt bị chia đôi qua hai chunk và tách khỏi bảng mà nó giải thích.
- Ba chunk của B (vị trí 1, 2, 9) được chấm 2 nhưng giáp ranh với 1, vì có hàng bảng lạc ở đầu chunk hoặc nhắc tới nội dung của đoạn trước. Nếu hạ cả ba, B còn 1,6/2, vẫn cao hơn A.
- So sánh này chưa tách bạch được ranh giới cắt với độ dài: chunk của B dài hơn A khoảng 21%.

**So sánh B–C (chỉ thêm filter).**

- Kết quả chỉ khác nhau ở các câu có filter. Ở dev, filter đưa q14 từ trượt thành trúng top-3 và q09 từ hạng 3 lên hạng 1. Ở test, filter đưa q30 từ hạng 3 lên hạng 1.
- Evidence Hit@3 tăng 1 câu ở dev (20 lên 21) và không đổi ở test (7/8). Hit@1 tăng 1 câu ở mỗi tập.
- Không có filter, top-3 hay lẫn nguồn ngoài phạm vi: B chỉ tuân thủ 0/4 câu ở dev và 2/3 ở test.
- Filter không giúp q18 và q20, vì top-3 của B ở hai câu này vốn đã nằm trong phạm vi.

**Metadata có hữu dụng không.**

- Truy vết: cả 45 bản ghi top-3 trên 5 câu test có `source`, `page`, `section`, `publisher`, `year` đúng với PDF gốc.
- Lọc: `publisher` đưa q14 (dev) từ trượt thành trúng và q30 (test) lên hạng 1; `section` đưa q09 (dev) lên hạng 1.
- Hạn chế: `publisher` quá thô cho q20 (xem ví dụ 3 bên dưới). `section` của các trang tóm tắt WHO là "Executive summary", đúng nhưng không cho biết trang nói về nhóm đối tượng nào. `page` là số trang vật lý của file, khác số in trên trang ở FM 7-22 (trang 57 in là "5-5") và WHO (trang 42 in là 32).

**Grounding (5 câu test, xét cả top-3).**

- A đạt 1,8/2: bốn câu điểm 2 và q16 điểm 1. B và C đạt 2,0/2.
- Nhãn tay khớp với Evidence Hit@3 tự động trên 5 câu này (A 4/5; B và C 5/5), nhưng chi tiết hơn: ở q16, top-3 của A có con số "twelve weeks" mà thiếu tên giai đoạn, nên là bằng chứng một phần chứ không phải không có.
- Điểm 2 không có nghĩa bằng chứng đứng đầu. Ở q18 (cả ba cấu hình) và q20 (B, C), đoạn đúng nằm ở hạng 3, sau các đoạn nêu con số khác hoặc nhóm đối tượng khác.
- Đây là đánh giá độ đủ của bằng chứng truy xuất, không phải độ chính xác câu trả lời của LLM.

**Ví dụ sai.**

1. **q29 (test, FM 7-22 trang 140), trượt ở cả ba cấu hình.** Câu hỏi về người quyết định cho quân nhân vào "Category 1 reconditioning". Top-3 gồm các đoạn nói chung về reconditioning ở trang 136, 137, 139. Chunk chứa evidence có tồn tại nhưng xếp ngoài top-3, nên đây là lỗi xếp hạng, không phải lỗi chunking.
2. **q16 (test, FM 7-22 trang 57), trượt ở A.** Chunk hạng 1 của A nằm đúng trang nhưng bắt đầu giữa từ: "d is the longest of all the periods lasting up to twelve weeks". Chunk có con số nhưng mất tên giai đoạn (BASE), nên không trả lời được câu "giai đoạn nào". B giữ được tiêu đề và trúng ở hạng 2.
3. **q20 (test, WHO trang 42), B và C chỉ trúng ở hạng 3.** Hai hạng đầu là khuyến nghị cho người cao tuổi (trang 14 và 53), gần như trùng lời với khuyến nghị cho người lớn 18–64 tuổi. Filter `publisher = WHO` quá thô để phân biệt; lọc theo `section` sẽ làm được, nhưng câu hỏi chỉ nêu "WHO".
4. **q03 (dev, FM 7-22 trang 44), trượt ở cả ba cấu hình.** Top-3 gồm các đoạn về hai hệ năng lượng khác ở trang 44–45 và một đoạn ở trang 61, không có đoạn về hệ phosphagen.

**Chiến lược chọn.** C, theo tiêu chí đã chốt: Evidence Hit@3 trên dev cao nhất (21/22, so với 20/22 của B và 17/22 của A). Trên test, C bằng B ở Evidence Hit@3 (7/8) và hơn 1 câu ở Hit@1 (4/8 so với 3/8). Nhãn tay không mâu thuẫn với lựa chọn này: C dùng chunk của B nên coherence 1,9/2 (A 1,0/2), và grounding 2,0/2 (A 1,8/2).

- Đánh đổi: C cần câu hỏi nêu rõ phạm vi và cần metadata đúng. Nếu người hỏi nêu sai phạm vi, filter cứng sẽ loại mất bằng chứng đúng. C không tốn thêm chi phí ingest vì dùng chung index với B.
- Điều kiện áp dụng: corpus có nhiều nguồn hoặc nhiều chương nói về cùng một chủ đề với con số khác nhau. Kết luận chỉ áp dụng cho corpus và bộ câu hỏi này.

**Hạn chế.**

- Test chỉ có 8 câu, mỗi câu tương đương 12,5 điểm phần trăm; chênh lệch 1 câu giữa B và C không đủ để kết luận chắc chắn.
- 20 trên 30 câu hỏi đến từ FM 7-22, nên kết quả chủ yếu phản ánh tài liệu này.
- Định nghĩa hit đòi chunk chứa trọn evidence nguyên văn, nên khắt khe với chunk chứa đúng ý nhưng thiếu vài chữ đầu (như q16 ở A).
- Tách đoạn bằng hình dạng dòng có lỗi đã biết: ở tài liệu WHO, nhãn "Strong recommendation…" bị gắn vào khuyến nghị kế tiếp thay vì khuyến nghị nó thuộc về.
- Nguy cơ rò rỉ giữa dev và test được liệt kê trong benchmark/README.md.
- Nhãn coherence, metadata và grounding do AI đề xuất và tác giả duyệt; cả hai đều biết chunk thuộc cấu hình nào và biết giả thuyết, nên nhãn có nguy cơ thiên lệch. Với grounding, bên đề xuất nhãn đã thấy kết quả hit tự động trước khi chấm. Thang ba mức cũng thô: mọi chunk của A đều rơi vào mức 1 ở coherence.
- Grounding chỉ chấm trên 5 câu; hai ca (q16 ở B và C) giáp ranh giữa 1 và 2.
- Câu q16 (test) mơ hồ: FM 7-22 trang 54 cũng gọi macrocycle là "the longest period, usually lasting a year or more", trong khi gold là giai đoạn base. Câu được giữ nguyên vì bộ test không sửa sau khi đã xem kết quả.
- Thời gian đo trên một máy tính xách tay và dao động giữa các lần chạy: embedding index A mất 44,0 giây ở lần dev và 40,1 giây ở lần test; một lần chạy dev trước đó (kết quả bị ghi đè, không còn file) mất 26,0 giây. Thời gian truy vấn chưa đo.

**Nếu làm lại hoặc mở rộng.**

- Thêm cấu hình đối chứng cửa sổ cố định 800 ký tự để tách ảnh hưởng của độ dài khỏi ranh giới cắt.
- Thử kết hợp tìm kiếm từ khóa (BM25) cho các câu có thuật ngữ đặc thù như q03 ("phosphagen") và q29 ("Category 1").
- Dùng công cụ đọc PDF có thông tin bố cục để tách đoạn và tiêu đề chính xác hơn.
- Viết thêm câu test, nhất là cho HHS và WHO.

**Phần học viên quyết định và tự làm.**

- **Chủ đề và corpus:** chọn chủ đề thể lực, quyết định dùng cả ba tài liệu và đặt trọng tâm vào FM 7-22. Vì vậy 20 trên 30 câu hỏi đến từ tài liệu này.
- **Dữ liệu trong repo:** quyết định commit PDF gốc sau khi đối chiếu quy định nộp bài.
- **Embedding model:** quyết định dùng `BAAI/bge-small-en-v1.5` chạy local.
- **Chấm tay:** tự chấm từng ca trong 20 ca coherence; duyệt 30 nhãn metadata và 15 nhãn grounding.
- **Benchmark:** đọc lại cả 30 câu hỏi cùng đáp án và evidence.
- **Kiểm soát tiến độ:** quyết định thời điểm commit, push và chuyển bước.

**Công cụ AI và cách kiểm tra.** Claude Code hỗ trợ viết code pipeline, soạn nháp bộ câu hỏi, đề xuất nhãn coherence, metadata, grounding, soạn nháp báo cáo này và dựng trang lab_walkthrough.html từ các file kết quả. Các kiểm tra tự động đã chạy: evidence của 30 câu so với corpus, tự kiểm tra cho chunking, cách chấm hit và vector store, chạy lại để so trace. Phần kiểm tra bằng tay do học viên làm, như liệt kê ở trên.
