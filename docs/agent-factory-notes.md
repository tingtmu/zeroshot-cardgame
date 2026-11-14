# Zeroshot 與「Agent Factory」筆記

整理日期:2026-11-14。來源是實際操作這個專案、本機 `repo/` 文件、和兩個 subagent 的查證。
標示【實測】= 我們親自跑過;【文件】= 文件寫的;【推測】= 沒有文件佐證。

## 1. 「Agent Factory」到底是什麼?

**結論:Zeroshot 文件沒有給「agent factory」一個明確定義。** 它比較像一個口號,實際上對應三個不同的層次:

| 層次 | 是什麼 | 狀態 |
|---|---|---|
| ① Graph run | 一個任務通過一張明確的 graph:worker 寫、獨立 verifier 審、失敗就回圈修、通過才交付 | 【實測】可用,Zeroshot 的核心 |
| ② 多任務串接 | `zeroshot-plan` 產生 `depends_on` 的計畫;`zeroshot stack` 依賴序送出 | 【文件】stack 只支援 hosted(Platform),本機與自架 Docker 都不行 |
| ③ Factory skills | `factory-collect / review-prs / ship / babysit-pr …`:從 issue、回饋、錯誤等訊號,依政策產生、審查、出貨變更 | 【文件】標示實驗性;repo 與網路上都找不到說明,只存在於已安裝的 skill |

### ① Graph run(Zeroshot 的核心)
- README 的主張:「一個讓 coding agent 不能自己驗收自己的多 agent 編排引擎」。
- 你把流程畫成 graph(誰寫、誰用乾淨 context 審、什麼必須通過、失敗回哪裡),引擎強制執行,agent 不能跳步。
- 內建 `software-change` 範本:`Worker → 並行審查(acceptance + code) → 交付`,迴圈上限 10 輪(只是安全上限,通過就立刻結束)。
- 完整範例圖(README):`Worker → 兩個審查 → E2E 測試 → PR → CI → Merge`,失敗回 Repair。

### ② 串接多個任務
- 本機沒有內建串接。stack 文件原話:「Stacks run on hosted targets… There is no local stack execution.」
- 原因文件沒說,也沒有本機版 roadmap。程式碼也明確拒絕 direct(自架)target:`direct target does not support hosted stacks`。
- 所以本機的做法是自己寫腳本依序呼叫 `zeroshot run`(見第 3 節)。這是膠水,不是 Zeroshot 的功能。

### ③ Factory skills
- 設計:訊號來源 → 收集分類 → 政策允許才修 → 隔離 worktree 驗證 → 開 PR → 審查 → 出貨。
- **每個動作的自主權限分開**:修好 issue 不代表自動授權回覆、核准、merge、部署或關閉 issue。
- 靠 host 的排程器觸發,沒有內建連接器清單。
- 它的重點是「持續從訊號產生變更」,不是「把 spec 的里程碑做完」。我們沒有實際使用它(你說你已經用過,細節以你的經驗為準)。

## 2. 「全自動」實際上是什麼意思
- 自動的是**一次 run 之內**:寫、測、審、修、(開 PR、等 CI、merge)。
- 仍然需要人的:寫 spec、切里程碑、選語言/模型/交付方式、一次性環境設定(CI、branch protection、gh 版本)、觸發下一個任務、事後看成果品質。
- 更準確的說法:把任務交出去,中間不用盯,回來看結果。

## 3. 這次實驗(zeroshot-cardgame)
- Repo:https://github.com/tingtmu/zeroshot-cardgame(公開),本機 `zeroshot/zeroshot-cardgame`。
- Spec:`spec.md`,Python + uv + pytest,回合制卡牌引擎,4 個里程碑。
- 全部 agent 用 `claude-haiku-5-5`、effort `medium`,以省用量。

| 里程碑 | 做法 | 結果 |
|---|---|---|
| 1 資料結構 | 本機、`--delivery none`;先用 Sonnet 跑、再用 Haiku 重跑 | 都成功;Haiku 67 測試通過,已 merge |
| 2 回合流程 | `cardgame-auto` profile,`--ship` | 第一次卡在交付(gh 太舊),補救後成功,PR #1 |
| 3 狀態效果 | 同上 | 一次成功,PR #2 |
| 4 敵人 AI | 同上 | 一次成功,PR #3 |

最終 `main`:【實測】`uv run pytest` 231 個測試全通過。
**未驗證**:沒有逐行讀過 Haiku 的程式碼;「固定種子可重現」和「新增卡牌不改引擎」只有 reviewer 的說法,我們沒獨立重做。

### 設定
- Profile:`cardgame`(預設,`--delivery none`)與 `cardgame-auto`(`--ship`,含專案專屬 reviewer 指令)。
- CI:`.github/workflows/ci.yml` 跑 `uv run --frozen pytest -q`,檢查名稱 `test`。
- `main` 有 branch protection,要求 `test` 通過;沒有要求人工 review(否則自動 merge 會卡住);管理員可繞過。
- 腳本(在 repo 外的 `runs/`):`run-milestones.sh [里程碑…]`,每次從 `origin/main` 切 `msN` 分支,`zeroshot run --profile cardgame-auto`,失敗即停。

## 4. 踩過的坑
1. **`gh` 太舊**:Zeroshot 交付用 `gh api graphql --paginate --slurp`,`gh 2.45.0` 不支援 `--slurp`,交付會失敗。apt 的版本仍是 2.45.0,所以改裝官方 release(2.104.0,核對 checksum)到 `~/.local/bin/gh`。之後你移除了 apt 版,並用 `gh auth setup-git` 把 git 的 credential helper 改指向新位置。
2. **`zeroshot resume` 送出後就返回**,不會等結果。我的腳本曾因此誤印「delivered」。判斷完成要用 `zeroshot status RUN_ID`。
3. **`zeroshot run` 沒有 `--worktree` 旗標**(這個版本)。改用切 feature branch;在目標分支(main)上直接跑會被拒絕。
4. 本機交付要求工作區乾淨;`submission-key` 重跑同一任務要換 key。
5. `--ship` 只會等 GitHub 上「必填」的檢查,沒設 branch protection 的話 CI 不會擋 merge。
6. `.venv`、`__pycache__` 等在不同分支的 `.gitignore` 不一致時,會讓切分支後工作區變髒。

## 5. 費用與資料
- CLI:MIT 授權、免費【文件】。README 稱不送遙測,只連 GitHub(安裝/更新)與你設定的模型供應商、Git 主機。
- 你讀到的官方說法(我未驗證):用現有 AI coding 訂閱(Claude/ChatGPT)在本機無限免費跑;Zeroshot Cloud 一次只跑一個任務免費(自備 API key),並行才付費(約 $100)。
- 我們這次花的是你的 Claude 用量;Zeroshot 本身沒收費。
- 不論 target 為何,agent 都會把需要的程式碼與上下文送給模型供應商【文件】。
- Platform 的保留期限、隱私條款:沒查到(官方網站在 subagent 端憑證驗證失敗)。
- 第三方網站的價格(「$100/user/month」)來源不明,不可採信。

## 6. 什麼時候才需要 Platform
本機 + 腳本對「單人、一次一個任務、電腦開著」已足夠。Platform 提供的是:不靠你的電腦跑、並行、伺服器端的 stack 排程、組織共用 profile/連線、issue 觸發與佇列【文件概述,未實際使用】。

## 7. 常用指令
```bash
export PATH="$HOME/personal-proj-wsl/software-factories/zeroshot/node_modules/.bin:$PATH"   # 已寫入 ~/.zshrc
zeroshot profile list
zeroshot run --title "…" --profile cardgame-auto --input INPUT.json --validate-only   # 先驗證
zeroshot run --title "…" --profile cardgame-auto --input INPUT.json --submission-key KEY
zeroshot status RUN_ID      # 判斷是否真的完成
zeroshot logs RUN_ID
zeroshot ui                 # http://127.0.0.1:4173/ui/
zeroshot checkpoints RUN_ID
zeroshot resume RUN_ID --from-checkpoint ID
```
檔案位置:`zeroshot/runs/`(graph.json、runtime.json、m1~m4-input.json、run-milestones.sh、各 log)。
