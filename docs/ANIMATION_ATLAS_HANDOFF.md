# Cobblemon Atlas｜動畫索引＋動作切換交接文件

> 2026-10-25｜Minecraft專案的跨對話執行依據。下一個對話請先讀本文件，再確認 GitHub 與使用者 Mac 上的程式目前版本；不要將規劃視為已實作。

## 1. 目標
在現有 GitHub Pages 圖鑑中，讓「每隻寶可夢的每個模型／形態」能選擇已產出的動作（待機、行走、飛行、游泳、戰鬥、哭叫等），播放對應動畫 WebP。採「先完整建立動作索引 → 優先渲染推薦動作 → 增量渲染其餘動作」，最終可涵蓋全部可支援動作，但**不一次盲目渲染所有動畫**。

## 2. 現況／已驗證事實
- 網站：https://hwh0410.github.io/cobblemon-atlas/ ，repo：`hwh0410/cobblemon-atlas`。現有整合頁 `index.html`、特殊形態頁 `mega-showdown/forms/index.html`。
- 目前 `mega-showdown/data/pokemon-animated.json` 約 1,170 筆（約 854 一般、316 特殊；以當時清單為準，實作前重新核對）。
- 先前比較卡片中有 128 筆特殊形態找不到同圖鑑編號的一般形態圖片，涉及 55 個圖鑑編號；本地唯讀盤點 55/55 均有模型與材質候選。已製作補渲染工具 `repair_55_base_webp.py`，使用者在 Mac 執行；後續完成狀態須再詢問/檢查，不可預設已全完成。
- 1,170 份 WebP 中約 457 份低於 15 KB，多數實際只有 1 幀。**大小不是動畫正確性的充分判據**。
- 用 `render_animated_portraits_v5_test.py` 測試：超級暴鯉龍有可見動畫，但洛奇亞、耿鬼失敗；之後 v6 測試使用者回傳耿鬼、超級暴鯉龍、洛奇亞 WebP，但尚未得到三者全部的正式影格檢測日誌及動作語義驗收，不可聲稱三者全驗證成功。
- 診斷證明洛奇亞 `air_idle` 有約 50 個疑似動態骨骼、49 個匹配模型，而 v5 選到的同名片段卻統計 0 動態通道，顯示 **development_resource_packs** 與 **merged_pack** 的資料來源／版本可能不同。原始 `tools/render_portraits.py` 的 `molang(expr,t)` 已正確使用角度制 sin/cos 與 q.anim_time 替換，但涵蓋的 MoLang 語法不完整。
- 普通耿鬼 `ground_idle`／`air_idle` 在提供的診斷樣本中是固定姿勢，`blink` 有短暫動作；不能硬將眨眼當作自然待機。
- 本地工作根目錄：`~/Downloads/cobblemon-render-lab/cobblemon-bedrock`；渲染環境：`$PWD/.venv/bin/python`。原始核心 `tools/render_portraits.py`。先前 v5 `~/Downloads/render_animated_portraits_v5_test.py`；v6 `~/Downloads/render_animated_portraits_v6_test.py`。若要修改，先取得使用者目前最新版原檔或上傳檔，不推測本地已存在未提供的檔案。

## 3. 技術原則
1. **模型／形態／動作分層**：同一圖鑑編號可有一般、Mega、Gmax、地區、性別等多模型；動畫 clip 的 key ≠ 前端顯示形態 ID。每個 renderer job 必須指定 model entity/form、clip、poser、來源路徑與渲染設定，避免把普通骨架的動畫錯套到 Mega 模型。
2. **同源資源**：動畫、Geo、Poser、Texture、Resolver 必須記錄資源包與來源版本；明確偵測不同 pack 同名 clip 衝突（prefer merged_pack if verified, otherwise audit）。
3. **靜態 GitHub Pages**：前端只能選擇已存在的 WebP，無法在訪客點選時現場執行 Python；未渲染動作可先顯示清單但置灰/提示「尚未產出」，不可展示假的播放鈕。需要即時渲染須另加後端，**不在首期範圍**。
4. **不破壞現有 WebP**：新動作輸出到獨立路徑，舊預設檔照常運作；採增量合併，不覆蓋原始 1,170 筆索引。
5. **只把實際可見變化視為動態成功**：渲染少量預覽幀檢查像素變化、模型仍完整、透明背景正確、循環無明顯跳動；`0` 變化的 clip 可保留 metadata 並標示 `static/pose`，不列為 playable 動態 WebP。
6. **支援有效動作，不保證全部 clip 有意義**：部分動畫是固定 pose、表情、特效、條件式或模型骨架不匹配；不要單用 namespace 推定可套用。

## 4. 資料設計（建議）
新增 `mega-showdown/data/animation-actions.json`（站點讀取用；或壓縮/分頁方案視實際大小而定）：
```json
{
  "schema_version": 1,
  "generated_at": "ISO-8601 timestamp",
  "source_version": "resource-pack version/hash",
  "entries": [
    {
      "form_id": "0249_lugia",
      "pokemon_id": "0249",
      "model_id": "0249_lugia",
      "display_name": "洛奇亞",
      "default_action_id": "air_idle",
      "actions": [
        {
          "id": "air_idle",
          "clip_key": "animation.lugia.air_idle",
          "label_zh": "空中待機",
          "category": "idle",
          "poser_path": "relative/source/path.json",
          "source_pack": "merged_pack",
          "duration_sec": 4.0,
          "loop": true,
          "dynamic_bones": 49,
          "model_bones_matched": 49,
          "status": "ready",
          "file": "mega-showdown/assets/pokemon-actions/0249_lugia/air_idle.webp",
          "bytes": 123456,
          "n_frames": 32,
          "changed_pixels_max": 1200
        }
      ]
    }
  ]
}
```
上例數值 `bytes / changed_pixels_max / n_frames` 是格式示意，**絕不可作為真實掃描結果**。初始掃描但未渲染者：`status: "pending"`、`file: null`、`bytes: null`；失敗者：`status: "static" | "failed" | "incompatible"` 搭配 `reason`。不應以檔名猜測 renderable，需經過實際驗證。

檔名規則：`mega-showdown/assets/pokemon-actions/{form_id}/{action_id}.webp`。若 `action_id` 名稱衝突（namespace、重名），加穩定 hash 後綴；不覆蓋舊 `mega-showdown/assets/pokemon-animated/`。單次 job 唯一鍵為 `form_id + clip_key + model/poser/source hash + render preset`。

分類／標籤：`idle`(待機)、`move`(移動)、`battle`(戰鬥)、`expression`(表情)、`rest`(休息)、`other`；根據 clip key 映射為繁體中文，未知名稱保留原文，勿錯標。

## 5. 渲染工作流程
### A. 掃描（先做）
新增 `tools/scan_animation_manifest.py`：
- 從既有網站 `pokemon-animated.json` 與本地 prepared entities／模型取得 **form_id** 清單；處理 55 隻補圖是否已完成。
- 對各 form 讀 Geo 骨架、Poser (優先專屬形態)、Resolver、animation JSON；輸出 clip 清單與來源 hash，辨識 keyframe／MoLang／靜態 pose。正確處理 `q.bedrock('x','y')` 的單雙引號與條件式配置；條件式需標為 conditional，不能任意假設生效。
- 檢查骨架匹配程度、原始 clip 長度、是否能 loop，計算候選分數；**動態骨骼數只能作初篩**，真正有效性需渲染確認。
- 輸出初版 action manifest（`pending`）以及報表：每 form 有多少個候選、具名動作、重名衝突與無匹配問題。
- 提供 `--dry-run` 與 `--forms`、`--all`，預設只讀不寫入正式站點。

### B. 小樣本品質驗證
新增 `tools/render_action_jobs.py` 支援 `--forms 0094_gengar 0249_lugia 0130_gyarados_mega --actions ...`，先測 `air_idle`, `air_fly`, `battle_idle`, `blink` 分類。固定畫面、錯位、被裁切、只有眼皮眨動必須正確分類。記錄 `status`、`n_frames`、`changed_pixels_max`、耗時、錯誤原因。動態品質驗證不能只比較檔案 KB 或只看第 1 幀。
- **基礎姿勢與實際動作可能需疊加**，但要遵守 Poser 定義，不可單純把所有 clip 相加。
- 留意 `animation_length` 缺失和 looping/keyframe 時間，MoLang `q.anim_time`。
- render 結束後利用 Pillow 開啟 WebP 回讀驗證，而非只驗證寫入前的影格。

### C. 分批渲染
- 第一輪：每 form 先 1 個預設待機、1 個代表移動／戰鬥（如實際可用）。
- 第二輪：特別形態專屬動作。
- 第三輪：全部其他相容且具意義的動作。
- 重跑支援 skip existing + source/settings hash、`--failed-only`、`--resume`、可中斷。將失敗報表列出，不得靜默略過。

## 6. 加速計畫與量測
先用 3-10 個形態實測基線秒／幀、讀檔、幾何建立、光柵化、WebP 編碼時間和記憶體。再依序：
1. 快取 JSON、模型骨架、UV/三角面、貼圖、Poser／動畫和 MoLang 編譯結果；避免每幀重新載入並重挑 clip。須確認渲染時每幀動態 transform 仍更新。
2. 每 form 使用固定構圖／視窗，避免每幀 fit 造成畫面縮放或抖動；適度 crop 但不能裁到肢體。
3. 小卡 192～224px、12–16fps；細節視情況 256px。先減少採樣超取樣 `ss`，驗證質感。
4. **跨 job 多進程**（不是同一檔 WebP 多程序亂寫），Mac 先試 2 workers，量測 RAM/吞吐後才調 3-4；不要保證任意加速倍率。Pillow 編碼可與渲染分階段量測。
5. 若實測 raster 瓶頸占主導，再評估 GPU (Metal、Blender、ModernGL／Colab)，**Colab GPU 不會自動加速現有 Python+numpy+Pillow 渲染器**；GitHub Pages 不能雲端按需生成。
6. Mac 闔蓋通常會睡眠，`nohup caffeinate -i` 也不保證閉蓋保持渲染。腳本具斷點續跑即可。

## 7. 網站 UI
- 在既有一般圖鑑與特殊形態卡片保持原有布局，圖片旁提供小型 **「動作」下拉選單**（桌面與手機都適用），預設為 `default_action_id`；資料只來自 manifest，切換立即更換 `<img src>`，並有 loading/error fallback。
- 已渲染：直接可選；未渲染：可選但標示「尚未產出」且留在原圖，或置灰（選定其一並在全站統一），不能生成不存在網址。
- 只下載目前顯示的動作 WebP；不要一次載入所有動作；切換時避免舊載入覆蓋新選擇。遵守 `prefers-reduced-motion` 及 `loading=lazy`。
- 同一寶可夢切換型態時重置/保留有效 action；特殊形態與一般形態不要共用不相容動作選項。
- 重要：維持既有「一般 vs 特殊形態」比較 UI 和「查道具」連結，不要一刀重寫首頁。

## 8. 驗收
1. manifest JSON 格式正確；所有 `ready` 的 `file` 存在、WebP 能解碼、動作確實可見；`pending` 不會生成 404。
2. 耿鬼、洛奇亞、超級暴鯉龍跨形態切換動作正常，不錯用普通骨架；具備非循環動畫時採正確播放策略。
3. 手機與桌面選單可用，圖片尺寸穩定不跳動，原有雙圖與道具連結正常。
4. 不重跑/覆蓋既有所有 WebP；新索引可增量更新且斷點續跑。
5. 加速依測量數字評估，避免以理論工作者數推估倍率。

## 9. 下一個對話的立即行動
1. 讀本文件與 GitHub 上的現有 `index.html`、`mega-showdown/forms/index.html`、`mega-showdown/data/pokemon-animated.json`，核對版面、現有 schema。
2. 檢查使用者已上傳的 `render_portraits.py`、`render_animated_portraits_v5_test(1).py`；如要直接修改本地 v6，向使用者取得 v6 現存檔或其原始碼；不可假設 GitHub 已有 v6。
3. **先實作 scan_animation_manifest.py（直接給可下載檔與 Mac 指令）**，先跑小樣本三隻，再讀回掃描報表。
4. 掃描資訊確認後，實作動作渲染器／少量輸出，最後才接 GitHub Pages 的動作下拉選單。
5. 可直接使用已連接的 GitHub 工具修改 `hwh0410/cobblemon-atlas`，但部署前確認使用者同意的改動範圍；掃描與本機渲染需在 Mac 上執行。

## 10. 新對話建議起始提示
「請依照 GitHub 專案 `hwh0410/cobblemon-atlas` 內的 `docs/ANIMATION_ATLAS_HANDOFF.md` 接續 Minecraft Cobblemon 動畫圖鑑工程。先讀交接文件、現有網頁及 manifest，再進行第一階段動畫資源完整掃描與 action manifest 產生器。現有 1,170 張 WebP 中約 457 張小於 15 KB，很多實際只有一幀；不要覆蓋舊圖；三隻測試：耿鬼、洛奇亞、超級暴鯉龍。請提供可以直接跑的腳本、測試方法與報表，再進行網站動作切換功能。」
