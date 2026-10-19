# 部署到公网（任何人、任何地方都能打开）

目标：把 DES Lab 变成一个公网网址，例如 `https://des-lab.streamlit.app`，手机、同事的电脑都能打开。

**一句话结论：**
- 想**免费、最快**上线 → **Streamlit Community Cloud**（用你的 GitHub 账号点几下就行）。
- 但它是"临时文件系统"：`user_data/` 里的记录会在应用重启/重新部署后**消失**。
- 如果记录必须长期保存 → 用**带持久磁盘的托管**（Render / Railway / 一台云服务器），或继续在本机跑 + 内网共享（`Start DES Lab (share).cmd`）。

---

## 方案 A · Streamlit Community Cloud（免费，10 分钟）

### 0. 先想清楚数据

Cloud 的容器是临时的：
- 用户注册、登录、保存的记录都能用；
- 但**应用休眠或重新部署后，`user_data/` 会重置**（账号和记录都会回到初始状态）。
- 所以 Cloud 适合"给别人看这个工具、演示流程"，不适合当长期正式数据库。

如果你要的是正式记录库 → 跳到方案 B / C。

### 1. 准备仓库

```powershell
# 在项目目录执行
git add -A
git commit -m "Prepare for deployment"
git push
```

- 入口文件已经加好：**`streamlit_app.py`**（Cloud 默认找这个名字）。
- 依赖已固定：`requirements.txt`。

### 2. 隐私检查（重要）

Cloud 要读你的仓库。仓库里这些文件会被**看到**：

| 路径 | 内容 | 公开前建议 |
| --- | --- | --- |
| `data/DES实验数据记录.xlsx` | 你的实验数据 | 建议移出仓库 |
| `data/Codex聊天记录_实验数据提取.md` | 含导师/同事姓名 | 建议移出仓库 |
| `README.zh.md` | 初始账号密码 `see DEPLOY.md - set it yourself (secrets / first sign-in)` | 公开前建议删掉密码 |

两种做法：
- **保持 private** + 在 Streamlit Cloud 授权访问私有仓库（推荐）；
- 或者**移出 `data/`** 后把仓库改成 public。

```powershell
# 若决定公开：先把私人数据移出仓库（文件仍留在本机）
git rm -r --cached data
"data/" >> .gitignore
git commit -m "Keep lab data out of the repository"
git push
```

### 3. 部署

1. 打开 <https://share.streamlit.io> → **Sign in with GitHub**（用 `feodore06-cyber`）。
2. **Create app** → *Deploy a public app from GitHub*。
3. 填：
   - Repository: `feodore06-cyber/des-lab`
   - Branch: `main`
   - Main file path: `streamlit_app.py`
4. **Advanced settings → Secrets**（强烈建议，一次填好）：

   ```toml
   DESLAB_HOSTED = "1"
   DESLAB_INVITE_CODE = "your-invite-code"

   [accounts]
   Chuanyu = "pick-a-strong-password"
   Thena = "another-strong-password"
   ```

   - `DESLAB_HOSTED=1`：侧边栏显示"记录会丢失"的警告；
   - `DESLAB_INVITE_CODE`：注册必须填邀请码，防止陌生人建号；
   - `[accounts]`：**首次启动时用这里的用户名和密码建立账号**——这样公网上不会出现 README 里那个已知密码。
5. **Deploy**，等 1–2 分钟，得到网址 `https://<你的名字>-des-lab.streamlit.app`。

> 也可以直接点 README 顶部的 **Deploy to Streamlit** 徽章，它会预填好仓库、分支和入口文件。

### 4. 上线后要做的事

- 立刻用 `Chuanyu` 登录，到 **Guide & Templates → Account & team** 改掉初始密码（README 里有明文）。
- 把网址发给同事；任何地方都能打开。

---

## 方案 B · 带持久磁盘的托管（记录长期保存）

以 **Render** 为例（免费额度有限，磁盘需付费档）：

1. 注册 <https://render.com>，连接 GitHub，选 `des-lab` 仓库。
2. 新建 **Web Service**：
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
3. 添加 **Disk**：挂载路径 `/opt/render/project/src/user_data`，大小 1 GB。
4. 设置环境变量 `DESLAB_DATA_DIR=/opt/render/project/src/user_data`、`DESLAB_HOSTED=1`。
5. 得到 `https://<name>.onrender.com`。

Railway / Fly.io / 一台云服务器（Ubuntu + Docker）同理：只要给 `user_data/` 一个**持久卷**即可。

> 注意：Streamlit 的会话状态在内存里，多实例之间不共享文件。**单实例 + 持久磁盘**是这套设计的正确用法。

---

## 方案 C · 从自己电脑暴露到公网（数据留在本机）

适合"临时给导师看一眼"，电脑必须开着。

```powershell
# 1) 本机先把应用跑起来
.\Start.ps1          # 或 Start DES Lab (share).cmd 让局域网也能访问

# 2) 另开一个窗口，用 Cloudflare 的免费隧道
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://127.0.0.1:8514
```

它会打印一个 `https://xxxx.trycloudflare.com` 的临时网址，任何人任何地方都能打开。
- 优点：数据 100% 留在你电脑上，不花钱。
- 缺点：网址每次重启都变；你的电脑关机就没了；速度依赖你家网络。

> 更省事的做法：直接双击项目里的 **`Start DES Lab (public tunnel).cmd`** —— 它会先启动网站、再开隧道，
> 窗口里会打出公网网址；**关掉窗口链接就失效**，下次启动网址会变。

---

## 我建议的顺序

1. **先要"能给别人看"** → 方案 A（Cloud），用 `DESLAB_INVITE_CODE` 锁住注册。
2. **要长期存正式实验数据** → 方案 B（带磁盘），或继续本机 + `Start DES Lab (share).cmd`（实验室内网共享）。
3. **临时演示给导师** → 方案 C（Cloudflare 隧道），最快最省钱。

---

## 部署前自检清单

- [ ] `streamlit_app.py` 存在（已在仓库里）
- [ ] `requirements.txt` 能装上（streamlit / pandas / matplotlib）
- [ ] `static/astar_logo.png` 在仓库里（开场动画、侧边栏要用）
- [ ] `data/` 里的私人数据是否要公开（**默认建议不公开**）
- [ ] README 里的初始密码是否要删
- [ ] 设置了 `DESLAB_INVITE_CODE`（公开部署时）
- [ ] 部署后用手机 4G 打开一次，确认不是只有 Wi-Fi 能用
