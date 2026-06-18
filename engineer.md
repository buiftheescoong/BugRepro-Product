# Kế hoạch cải thiện ReBugger để ứng tuyển AI Engineer Fresher/Junior

## 1. Mục tiêu

Mục tiêu là biến project **ReBugger - Web Agent for Automated Bug Reproduction** thành project chủ lực trong CV khi ứng tuyển các vị trí **AI Engineer Fresher/Junior**, đặc biệt là các hướng:

- Applied AI Engineer
- LLM Engineer
- AI Agent Engineer
- Generative AI Engineer
- AI Engineer làm sản phẩm nội bộ, QA automation, RAG, agent, workflow automation

Project hiện tại đã có nền tảng tốt: Python, FastAPI, LangGraph, Playwright, ChromaDB, Docker, frontend, benchmark embedding, Planner/Critic/Executor. Vì vậy không nên làm thêm quá nhiều project rời rạc ngay lập tức. Việc quan trọng hơn là làm project này trông giống một **hệ thống AI hoàn chỉnh, có thể demo, có thể đo lường, có thể debug và có thể giải thích khi phỏng vấn**.

Các tín hiệu nhà tuyển dụng AI Engineer thường tìm:

- Biết build ứng dụng AI end-to-end, không chỉ gọi API LLM.
- Có kinh nghiệm với LLM, prompt engineering, tool calling, RAG, vector database.
- Biết Python backend, API, Docker, logging, SQL/database.
- Biết đánh giá hệ thống AI bằng metric, benchmark, ablation study.
- Biết xử lý lỗi thực tế: hallucination, timeout, selector fail, action fail, model claim sai.
- Có demo và tài liệu rõ ràng để người khác chạy hoặc hiểu nhanh.

## 2. Chiến lược tổng thể

Không mở rộng project theo kiểu thêm thật nhiều tính năng không liên quan. Nên tập trung vào 5 hướng chính:

1. **Demo rõ ràng**: nhà tuyển dụng mở GitHub là hiểu project trong 3 phút.
2. **Trace và report**: mỗi lần agent chạy phải có bằng chứng từng bước.
3. **Evaluation**: có benchmark, metric, so sánh mô hình và ablation.
4. **Reliability**: thể hiện bạn hiểu các lỗi thường gặp của AI agent và có cách giảm lỗi.
5. **CV assets**: chuẩn bị sẵn bullet, bảng metric, failure analysis để dùng khi apply/phỏng vấn.

## 3. Những phần cần build thêm vào project hiện tại

### 3.1. Public demo package

Cần build:

- Viết lại hoặc bổ sung phần README tiếng Anh.
- Thêm ảnh kiến trúc hệ thống hoặc sơ đồ Mermaid.
- Thêm demo video/GIF 2-3 phút.
- Thêm 3 demo scenario mẫu:
  - Bug validation/form.
  - Bug routing/access control.
  - Bug stale UI/modal/dropdown.
- Thêm hướng dẫn chạy nhanh bằng Docker.

Vì sao cần làm:

Recruiter và interviewer thường không có thời gian đọc toàn bộ code. Một demo package tốt giúp project tạo ấn tượng ngay lập tức. Với fresher/junior, khả năng trình bày project rõ ràng đôi khi quan trọng ngang với độ phức tạp kỹ thuật.

Kết quả mong muốn:

- Người xem hiểu project giải quyết vấn đề gì trong dưới 1 phút.
- Người xem biết cách chạy project trong vài command.
- Có demo trực quan cho thấy agent nhận bug report, thao tác browser và kết luận kết quả.

### 3.2. Structured agent trace

Cần build:

- Lưu lại từng bước agent chạy dưới dạng có cấu trúc.
- Mỗi trace step nên có:
  - `thread_id`
  - `step_index`
  - `node`: Perception, Planner, Critic, Executor
  - `current_url`
  - `screenshot_path`
  - `proposed_action`
  - `critic_decision`
  - `critic_reason`
  - `executor_result`
  - `error_type`
  - `latency_ms`
  - `input_tokens`
  - `output_tokens`
  - `created_at`
- Thêm API để xem trace theo run:
  - `GET /runs/{thread_id}/trace`
  - `GET /runs/{thread_id}/metrics`
  - `GET /runs/{thread_id}/report`

Vì sao cần làm:

AI agent rất dễ bị coi là "black box". Nếu project có trace rõ ràng, bạn chứng minh được mình không chỉ biết gọi LLM mà còn biết quan sát, debug và vận hành hệ thống AI.

Kết quả mong muốn:

- Mỗi run có thể replay lại bằng timeline.
- Khi agent fail, biết fail ở bước nào và vì sao.
- Khi phỏng vấn, bạn có thể mở trace để giải thích Planner/Critic/Executor phối hợp thế nào.

### 3.3. Reproduction report generator

Cần build:

- Tạo report sau mỗi lần chạy agent.
- Report nên có bản Markdown và JSON.
- Nội dung report gồm:
  - Bug description.
  - Root URL.
  - Target screenshot.
  - Final status: success, failed, need_input, error.
  - Các bước reproduce ở dạng người đọc hiểu được.
  - Evidence screenshot.
  - Critic verification.
  - Failure reason nếu không reproduce được.
  - Metrics: số bước, latency, số lần gọi LLM, token usage.

Vì sao cần làm:

Project sẽ chuyển từ "agent demo" thành một công cụ có giá trị thực tế cho QA/dev team. Đây là điểm rất mạnh khi apply AI Engineer vì nó thể hiện khả năng biến AI thành workflow sản phẩm.

Kết quả mong muốn:

- Có thể copy report vào GitHub issue, Jira ticket hoặc tài liệu QA.
- Failed run vẫn hữu ích vì có failure reason và last known state.

### 3.4. Evaluation framework v2

Cần build:

- Chuẩn hóa lại cách chạy benchmark.
- Có một command rõ ràng để chạy evaluation.
- Có một command rõ ràng để phân tích kết quả và sinh report.
- Metric nên có:
  - Reproduction Success Rate.
  - RSR@1.
  - Success-claim precision.
  - Average steps.
  - p50/p95 latency.
  - Token usage.
  - Estimated cost per run nếu dùng API model.
  - Failure category distribution.
- Ablation nên có:
  - Planner-only vs Planner+Critic.
  - No-memory vs ChromaDB memory.
  - DOM-only vs screenshot+DOM.
  - So sánh Gemini/GPT/Qwen/Gemma nếu có dữ liệu.
  - So sánh các embedding models.

Vì sao cần làm:

Đây là phần gây ấn tượng mạnh nhất với vị trí AI Engineer. Rất nhiều ứng viên có chatbot hoặc RAG demo, nhưng ít người có benchmark, metric và ablation nghiêm túc.

Kết quả mong muốn:

- Có file `docs/evaluation.md` tóm tắt kết quả.
- Có bảng metric ngắn để đưa vào CV.
- Có biểu đồ hoặc bảng so sánh để dùng khi phỏng vấn.

### 3.5. Reliability layer cho agent actions

Cần build:

- Validate action schema trước khi executor chạy.
- Chuẩn hóa lỗi thành các nhóm:
  - `SELECTOR_NOT_FOUND`
  - `ACTION_TIMEOUT`
  - `NAVIGATION_FAILED`
  - `AUTH_REQUIRED`
  - `UNSUPPORTED_WIDGET`
  - `LLM_INVALID_ACTION`
  - `BUG_NOT_REPRODUCED`
- Thêm retry policy cho:
  - Element chưa visible.
  - Element bị che bởi modal.
  - Click bị intercept.
  - Navigation timeout.
  - Selector stale.
- Thêm fallback locator:
  - CSS selector chính.
  - Role/text locator.
  - XPath.
  - Coordinate fallback chỉ dùng cuối cùng.

Vì sao cần làm:

AI agent thực tế thường fail vì các lỗi nhỏ khi thao tác browser. Nếu project có reliability layer, bạn thể hiện tư duy engineering tốt hơn hẳn việc chỉ dùng prompt để agent tự đoán.

Kết quả mong muốn:

- Invalid action không làm crash toàn bộ run.
- Lỗi được ghi lại trong trace.
- Critic/Planner nhận được feedback có cấu trúc để re-plan.

### 3.6. RAG memory upgrade

Cần build:

- Làm rõ memory schema:
  - Bug type.
  - App/domain.
  - Successful actions.
  - Failed actions.
  - Final status.
  - Tags.
  - Embedding text.
- Khi retrieve memory, cần trả về:
  - Similar bug id.
  - Similarity score.
  - Useful past action.
  - Failed path to avoid.
- Thêm reranking đơn giản:
  - Ưu tiên cùng domain/app.
  - Ưu tiên case success.
  - Giảm điểm các case failed không liên quan.

Vì sao cần làm:

RAG/vector database là keyword xuất hiện nhiều trong JD AI Engineer. Project của bạn đã có ChromaDB và embedding benchmark, nhưng cần làm rõ RAG giúp agent tốt hơn như thế nào.

Kết quả mong muốn:

- Report ghi rõ memory có được dùng hay không.
- Evaluation có ablation no-memory vs memory.
- README có section giải thích thiết kế RAG memory.

### 3.7. Production API và config cleanup

Cần build:

- Thêm `.env.example`.
- Chuyển các config quan trọng sang environment variables:
  - Planner model.
  - Critic model.
  - Max steps.
  - Headless mode.
  - Storage mode.
  - Memory path.
  - CORS origins.
- Thêm các endpoint:
  - `GET /health`
  - `GET /models`
  - `GET /config/public`
- Có local storage fallback cho screenshot khi không dùng cloud storage.

Vì sao cần làm:

Project chạy được trên máy người khác là điểm cộng lớn. Nếu bắt buộc có quá nhiều secret/cloud config thì recruiter hoặc interviewer khó thử project.

Kết quả mong muốn:

- Có thể chạy demo local không cần cloud storage.
- API docs rõ ràng trên FastAPI `/docs`.
- Config không hard-code trong code.

### 3.8. Frontend trace dashboard

Cần build:

- Thay terminal log đơn giản bằng timeline rõ ràng hơn.
- Mỗi step hiển thị:
  - Node name.
  - Screenshot.
  - Planner action.
  - Critic approve/reject.
  - Executor result.
  - Latency/tokens nếu có.
- Thêm panel metric cho run:
  - Status.
  - Total steps.
  - Latency.
  - Token usage.
  - Model names.
- Thêm nút download report.
- Thêm so sánh target screenshot vs current screenshot.
- Thêm filter history theo status.

Vì sao cần làm:

Frontend không cần quá đẹp, nhưng cần giúp người xem hiểu agent đang làm gì. Với Applied AI Engineer, demo end-to-end là lợi thế lớn.

Kết quả mong muốn:

- Quay demo video chỉ bằng frontend là đủ.
- Người xem không cần đọc backend log vẫn hiểu agent chạy thế nào.

### 3.9. Testing và CI

Cần build:

- Unit test cho:
  - Parser/action schema.
  - Memory formatting.
  - Report generator.
  - Error taxonomy.
- API test cho:
  - `/health`
  - `/history`
  - `/runs/{thread_id}/trace`
  - `/runs/{thread_id}/metrics`
  - `/runs/{thread_id}/report`
- Mock LLM test cho graph flow cơ bản.
- GitHub Actions chạy backend test và frontend build.

Vì sao cần làm:

Test và CI giúp project trông nghiêm túc hơn. Đây là tín hiệu tốt cho junior vì nó cho thấy bạn biết làm code maintainable.

Kết quả mong muốn:

- `pytest` chạy được mà không cần gọi LLM thật.
- CI badge xuất hiện trong README.
- Test không phụ thuộc API key mặc định.

## 4. Thứ tự ưu tiên triển khai

### Giai đoạn 1: Làm project dễ hiểu và dễ demo

1. Viết README tiếng Anh.
2. Thêm architecture diagram.
3. Thêm `docs/demo.md`.
4. Chuẩn bị demo video/GIF.
5. Thêm `.env.example`.

Ưu tiên này giúp project pass vòng CV tốt hơn ngay cả khi chưa có thêm nhiều code mới.

### Giai đoạn 2: Thêm trace và report

1. Thiết kế structured trace schema.
2. Lưu trace cho từng node Perception/Planner/Critic/Executor.
3. Thêm API trace/metrics/report.
4. Sinh reproduction report Markdown/JSON.
5. Hiển thị report cơ bản trên frontend.

Đây là phần nên làm sớm nhất nếu muốn project nổi bật về AI Agent engineering.

### Giai đoạn 3: Chuẩn hóa evaluation

1. Gom benchmark hiện có thành một pipeline dễ chạy.
2. Sinh summary report tự động.
3. Thêm bảng ablation.
4. Thêm failure category.
5. Viết `docs/evaluation.md`.

Đây là phần dùng trực tiếp cho CV bullets và phỏng vấn.

### Giai đoạn 4: Tăng reliability

1. Validate action schema.
2. Thêm error taxonomy.
3. Thêm retry/fallback cho browser actions.
4. Cho Critic dùng feedback có cấu trúc.
5. Đánh giá lại sau khi thêm reliability layer.

Phần này giúp project khác biệt với các demo agent đơn giản.

### Giai đoạn 5: Nâng frontend và CV assets

1. Làm timeline trace view.
2. Thêm metric panel.
3. Thêm download report.
4. Thêm `docs/cv_assets/project_summary.md`.
5. Thêm `docs/cv_assets/interview_talking_points.md`.
6. Chốt lại CV bullets.

## 5. CV bullets nên hướng tới sau khi cải thiện

Sau khi hoàn thành các cải tiến chính, có thể viết project trong CV theo hướng:

- Built an autonomous multimodal web agent that reproduces UI bugs from natural-language reports and target screenshots using LangGraph, FastAPI, Playwright, Docker, and ChromaDB.
- Designed a Perception-Planner-Critic-Executor workflow with structured tool calling, browser action validation, screenshot/DOM grounding, and trajectory logging.
- Created a 100-bug benchmark across 4 web apps and evaluated reproduction success rate, RSR@1, success-claim precision, latency, token usage, and failure categories.
- Improved agent reliability with Critic-based action review, structured error taxonomy, retry handling, selector fallback, and RAG memory over past successful/failed reproductions.
- Benchmarked 10 embedding models and selected BGE-M3 for multilingual bug-memory retrieval.

## 6. Có cần làm thêm project khác không?

Chưa nên làm thêm project khác ngay. Project này đã đủ tiềm năng để làm flagship project cho Applied AI/LLM Agent roles.

Chỉ nên làm thêm project thứ hai sau khi project này có:

- README/demo tốt.
- Trace/report rõ ràng.
- Evaluation report có metric.
- Docker/local demo chạy được.
- CV bullets gắn với kết quả thật.

Nếu sau đó vẫn muốn làm project phụ, nên làm một project nhỏ về **Document Intelligence / OCR + LLM Extraction + RAG** để bao phủ thêm nhóm JD enterprise AI. Nhưng project phụ không nên lấy thời gian của các phần cốt lõi ở ReBugger.

## 7. Definition of Done

Project được xem là đủ mạnh để đưa vào CV khi đạt các điều kiện:

- Người xem GitHub hiểu project trong dưới 3 phút.
- Có demo video/GIF rõ ràng.
- Có thể chạy bằng Docker hoặc hướng dẫn local rõ ràng.
- Mỗi agent run có trace và report.
- Có benchmark/evaluation report với metric thật.
- Có ablation cho Critic, RAG memory hoặc multimodal input.
- Có failure analysis, không chỉ báo success.
- CV metrics lấy từ file kết quả trong repo, không viết thủ công.
- Khi phỏng vấn, có thể giải thích rõ vì sao dùng LangGraph, Critic, RAG, Playwright và ChromaDB.

## 8. Kết luận

Hướng cải thiện tốt nhất là biến ReBugger thành một project AI Agent có tính sản phẩm và có đánh giá nghiêm túc. Không cần vội làm thêm nhiều project. Nếu hoàn thiện trace, report, evaluation, reliability và demo, project này đủ để gây ấn tượng mạnh với các vị trí AI Engineer Fresher/Junior theo hướng Applied AI, LLM Agent và GenAI system.
