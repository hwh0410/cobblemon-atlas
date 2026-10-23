# Cobblemon Atlas · 1.3.2

適用 Minecraft Java 1.19.2 / Forge 與 Cobblemon 1.3.2 的靜態隨身圖鑑。

## 內容

- 依全國編號、名稱、屬性、實裝標記、是否有自然生成規則等篩選 1,010 筆物種資料。
- 依原始 JAR 中的 570 筆進化設定與生成資料展示條件；保留無法確定的原始 JSON。
- Minecraft / Cobblemon 指令複製與操作指引。
- 本機捕捉與異色追蹤、座標、備註、JSON 備份匯入匯出以及 CSV 匯出。

## 部署到 GitHub Pages

1. 建立 **public** repository，建議名稱 `cobblemon-atlas`。
2. 把本資料夾的 **所有檔案與 `data/` 子目錄** 放在 repository 根目錄。
3. GitHub repository → Settings → Pages → Build and deployment: **Deploy from a branch** → `main` / `/(root)` → Save。
4. 網址通常為 `https://<your-account>.github.io/cobblemon-atlas/`。

亦可在本機進行預覽：

```bash
cd cobblemon-companion
python3 -m http.server 8000
# 開啟 http://localhost:8000
```

## 資料說明

來源為使用者提供之 Cobblemon 1.3.2 JAR 擷取 CSV：

- 01_寶可夢圖鑑.csv：1,010 筆
- 02_進化條件_原始資料.csv：570 筆
- 03_自然生成棲地_原始資料.csv：546 筆

圖鑑顯示的主形態生成匹配為 499 筆，其餘 47 筆涉及阿羅拉、特殊形態或其他變體的名稱，**未直接合併到基礎物種，避免誤導**。原檔「實裝」只有 `true` 才顯示「明確已實裝」，缺少標記不是「未實裝」的證據。

網頁會儲存進度在 localStorage，不跨瀏覽器同步，務必定期匯出 JSON。不是官方產品。
