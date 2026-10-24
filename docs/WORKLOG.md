# Nhật ký công việc: AI Learning Assistant

_Ngày: 2026-10-24 · Nhánh: `langgraph-ui` (tách từ `langgraph`) · Repo: https://github.com/ViHa0509/AI_DEMO_

File này tóm tắt những gì đã làm, lý do và kết quả kiểm tra. Chi tiết kỹ thuật cho người tiếp quản xem [HANDOFF.md](HANDOFF.md); hướng dẫn deploy xem [DEPLOYMENT.md](DEPLOYMENT.md).

## ⚠️ Việc bạn cần làm ngay

1. **Đổi 3 key bị lộ**: HuggingFace (`hf_…`), Tavily (`tvly-…`), LangSmith (`lsv2_…`). Chúng vẫn nằm trong lịch sử git, và **repo đang public** nên ai cũng đọc được.
2. Khi có OpenAI key: thêm GitHub secrets `HF_TOKEN`, `OPENAI_API_KEY`, `APP_PASSWORD` theo [DEPLOYMENT.md](DEPLOYMENT.md), rồi chạy workflow.

---

## Phần 1: Review branch `langgraph`

Branch gốc **không chạy được**. Các lỗi chính:

| # | Lỗi | Hậu quả |
|---|---|---|
| 1 | Node `router` trả về key `next` mà `State` không có | Mọi tin nhắn đều lỗi |
| 2 | `classify_message` trả về `None` khi LLM trả lời lạ | Graph lỗi |
| 3 | Gọi `VirusTotalChecker.is_url_safe()` trên class, không tạo instance | Mọi lần crawl đều crash |
| 4 | Logic VirusTotal đọc kết quả khi chưa quét xong | URL mới luôn bị coi là "unsafe" |
| 5 | `main.py` mở `prompt.yaml` sai thư mục | Không có prompt |
| 6 | `import IPython` không có trong requirements | Crash khi khởi động |
| 7 | `store.py` dùng biến `embeddings` chưa định nghĩa | Không nạp được dữ liệu |
| 8 | Prompt `extract_data_1` bảo LLM **tự bịa** bài báo | Kết quả crawl sai sự thật |
| 9 | Excel dùng ô gộp (merged cells), code bỏ qua các dòng tiếp theo | **Mất toàn bộ sheet AI** và nhiều mô tả ở sheet khác |
| 10 | Thiếu timeout HTTP, model embedding load lại mỗi câu hỏi, `score_threshold` bị bỏ qua, thiếu nhiều package | Chậm, dễ treo, khó cài |

## Phần 2: Tổ chức lại code và sửa lỗi

- Gom code vào package `app/`: config, prompts, llm, retriever, crawler, url_scanner, graph, server.
- Graph mới đi thẳng `classifier → agent`; nếu LLM phân loại lạ thì dùng từ khóa để đoán (hỗ trợ cả tiếng Việt).
- Lịch sử hội thoại theo `thread_id` (LangGraph `MemorySaver`).
- Search agent tóm tắt kết quả Tavily và trích nguồn.
- Crawler: đọc được mọi trang (không chỉ Blogger), có timeout, chặn localhost/mạng nội bộ (SSRF).
- Thiếu key thì agent trả lời rõ "chưa cấu hình" thay vì crash.
- Viết lại `prompt.yaml` (bỏ prompt thừa, trả lời theo ngôn ngữ người dùng), `requirements.txt`, `.env.example`.
- Bỏ `.env` khỏi git.

## Phần 3: Giao diện web

FastAPI backend và frontend HTML/CSS/JS thuần (không cần build):

- Câu trả lời hiện dần theo thời gian thực (streaming).
- Badge cho biết agent nào trả lời, chip nguồn tham khảo.
- Render Markdown, tô màu code, nút copy.
- Danh sách hội thoại, nút dừng, giao diện sáng/tối, dùng được trên mobile.
- Sidebar hiện model đang dùng và tính năng nào đã cấu hình.

## Phần 4: Deployment

**Lựa chọn:** Hugging Face Spaces (Docker, free 16GB RAM) + GitHub Actions. Lý do: model embedding cần torch (~1GB RAM), các host free 512MB khác sẽ hết RAM.

| Hạng mục | Đã làm |
|---|---|
| Database | **Không cần DB ngoài**: app tự nhúng `LearningPath.xlsx` vào vector store trong bộ nhớ, index dựng sẵn khi build Docker. PGVector vẫn dùng được nếu đặt `PGVECTOR_CONN`. Sửa lỗi ô gộp: giờ có 378 kỹ năng, gồm cả sheet AI |
| Bảo vệ | `APP_PASSWORD`: màn hình đăng nhập, token ký HMAC, giới hạn số request mỗi phút. Deploy script **từ chối** deploy Space public nếu thiếu mật khẩu (tránh bị đốt quota OpenAI) |
| Docker | `Dockerfile` dùng torch bản CPU (nhẹ hơn ~1.5GB), chạy user uid 1000, có healthcheck |
| CI/CD | `.github/workflows/ci-cd.yml`: Tests → Build Docker + smoke test → Deploy (chỉ khi push `main` hoặc bấm chạy tay) |
| Deploy script | `deploy/deploy_space.py`: tự tạo Space, đồng bộ secrets/variables từ GitHub, upload code |
| Test | 32 test pytest, không cần mạng (dùng LLM giả) |

## Commits (đã push lên `origin/langgraph-ui`)

| Commit | Nội dung |
|---|---|
| `de02490` | chore: bỏ theo dõi `.env`, thêm `.env.example`, bổ sung requirements |
| `b6f4500` | refactor: gom vào package `app/`, sửa lỗi định tuyến/VirusTotal/crawler |
| `1c47131` | fix(vectordb): sửa script nạp dữ liệu |
| `8387a36` | feat: backend FastAPI + giao diện web streaming |
| `0f48fdf` | docs: README và handoff |
| `472099b` | feat: knowledge base trong bộ nhớ, sửa lỗi ô gộp Excel |
| `0d28619` | feat: đăng nhập bằng mật khẩu + giới hạn request |
| `0221e62` | test: bộ test pytest |
| `b15a161` | ci: Dockerfile + GitHub Actions + deploy script |
| `15f36bb` | docs: DEPLOYMENT.md, cập nhật README/HANDOFF |

Tác giả commit được ghi là `Petrus.Ha <petrus.ha@laidon.com>` vì máy chưa cấu hình git identity (không sửa git config).

## Đã kiểm tra những gì

| Hạng mục | Kết quả |
|---|---|
| Định tuyến 4 agent, streaming, lịch sử hội thoại | ✅ Với LLM giả lập |
| Giao diện (gửi tin, stream, lưu lịch sử, 2 theme, đăng nhập) | ✅ Điều khiển Edge headless và chụp màn hình |
| Crawler trên trang thật, chặn URL nội bộ | ✅ |
| 32 test pytest | ✅ Pass trên máy local |
| Deploy script (dry-run, chặn khi thiếu mật khẩu) | ✅ |
| CI trên GitHub (test + build Docker + smoke test) | ✅ Pass, xem bên dưới |
| LLM thật (OpenAI), Tavily, VirusTotal | ❌ Chưa có key |
| Deploy thật lên HF Spaces | ❌ Chưa có `HF_TOKEN` |

### Kết quả CI

[Run 40100716473](https://github.com/ViHa0509/AI_DEMO/actions/runs/40100716473) trên commit `15f36bb`:

| Job | Kết quả | Thời gian |
|---|---|---|
| Tests (32 test, Linux, thư viện thật) | ✅ success | ~2.5 phút |
| Docker build + smoke test | ✅ success | ~4 phút |
| Deploy to Hugging Face Spaces | ⏭️ skipped (đúng thiết kế: chỉ chạy trên `main` hoặc khi bấm chạy tay) | |

Smoke test đã xác nhận: image build được (kể cả tải model embedding và dựng index), container khởi động, `/api/health` trả về `auth_required: true` và `knowledge_backend: in-memory`, giao diện trả về 200, và `/api/chat` không có token thì trả về 401.

## Lưu ý về máy Windows này

Windows Application Control chặn DLL của `xxhash`, `ormsgpack`, `jiter`, `msgpack` (và có thể cả torch), nên LangGraph không chạy trực tiếp được trên máy này. Khi test, mình dùng bản thay thế Python thuần đặt trong thư mục tạm, **không nằm trong repo**. Trong Docker/HF Spaces (Linux) không gặp vấn đề này.

## Bước tiếp theo

1. Đổi 3 key bị lộ.
2. Tạo token HF, thêm GitHub secrets theo [DEPLOYMENT.md](DEPLOYMENT.md), vào **Actions → CI/CD → Run workflow** chọn `langgraph-ui` để deploy thử.
3. Thử chat thật với từng agent.
4. Mở PR `langgraph-ui` → `main`; merge xong thì mỗi lần push `main` sẽ tự deploy.
