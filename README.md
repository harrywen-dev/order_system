# 午餐一起訂

員工午餐外送 MVP：FastAPI、React / TypeScript、PostgreSQL 17。

## 規則

所有員工可發起店家提案，提供日期、店家連結、菜單文字或連結，以及自行與店家確認的最低外送份數。員工填寫預計訂購份數，同姓名對同提案重新提交會覆蓋，填 0 撤回。

每天第一位發起人設定共用的募集與投票截止時間。後續提案必須沿用。募集截止後，只有一家達標則直接選定；多家達標則每人一票，可改投；沒有達標則不開放點餐。投票截止後最高票勝出，同票（含零票）採最早提案。

發起人設定自己提案的點餐開啟與截止時間，須滿足「募集截止 < 投票截止 ≤ 點餐開啟 < 點餐截止」。正式點餐僅開放當天勝出店家。每人目前可提交一筆餐點及份數，截止前可覆寫或取消。實際訂購份數低於門檻會顯示提示，不會自動替店家下單。提供彙總及 CSV 匯出。

所有時間在 API 使用含時區的 ISO 格式；介面顯示台北時間，時間輸入依裝置時區。流程由伺服器時間判定，不依賴排程器；介面每 15 秒更新。

## 啟動（Windows / macOS / Linux，需 Docker Desktop 或 Docker Engine）

複製 `.env.example` 為 `.env`，將 `POSTGRES_PASSWORD` 換成隨機密碼（僅英數字，避免 URL 特殊字元）。

```sh
docker compose up -d --build
```

前端使用 8080 埠，透過 Nginx 代理 `/api` 至 FastAPI。資料庫使用 Docker volume 持久化，不對外公開埠。

```sh
docker compose down                 # 停止，保留資料
docker compose logs --tail 50       # 診斷
```

`docker compose down -v` 會永久刪除資料，請勿當成一般停止指令。

## 雲端開發

```sh
bash scripts/setup.sh
bash scripts/start-cloud.sh
cd backend
../.venv/bin/python -m pytest tests -q
cd ../frontend
npm run build
```

雲端腳本使用可寫入的 npm / Docker 設定目錄，並在宿主機安裝依賴、啟動 FastAPI 與 Vite，PostgreSQL 使用 Docker。雲端容器建置的 DNS 不可用，因此雲端採此方式，保留 TLS 驗證。一般電腦使用標準 compose 指令即可。

如需熱更新，可另啟動 FastAPI（8000 埠）與 Vite（5173 埠），Vite 已設定 API 代理。設定 `DATABASE_URL` 使用 PostgreSQL；未設定時僅開發使用 SQLite。

## 目前限制與正式上線前工作

這是內部試用 MVP，以姓名識別，沒有登入或權限驗證。使用者可冒用他人姓名，訂單彙總對所有使用者可見。正式上線前應加入公司 SSO／員工帳號及伺服器授權，並設定 HTTPS、資料庫備份、資料遷移。請勿直接公開至網際網路供正式使用。

菜單目前為文字／連結，點餐餐點与單價由員工填寫；尚無圖片上傳、結構化品項、付款、通知或店家下單整合。訂餐時間在發布後不可編輯。同票及共用截止時間規則為第一版預設。

部署可採單台主機 Docker Compose，或 React 靜態部署 + FastAPI 容器 + 託管 PostgreSQL（Neon / Supabase）。切換資料庫使用 `DATABASE_URL`；既有資料不會自動搬移。

驗證：5 項後端測試在 SQLite 與專用 PostgreSQL 測試資料庫各通過一次，前端 TypeScript 與 Vite production build 通過。Rollup 固定為 4.40.2，避免 4.64.2 在此環境建置時卡住。使用 TEST_DATABASE_URL 執行 PostgreSQL 測試時，請指向可清空的專用測試資料庫，測試會重建資料表。
