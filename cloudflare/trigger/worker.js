// 티커맵 수집 깨우미 — Cloudflare Worker (Cron Triggers)
//
// 깃허브 예약 실행은 몇 시간씩 늦기도 해서, 정확한 시각에 hub 워크플로를 workflow_dispatch로 깨움.
// Cloudflare 크론은 UTC 기준이라 서머타임 두 경우를 모두 등록해 두고, 여기서 뉴욕 현지 시각을 보고 고름.
//
//   크론 트리거 (4개, UTC):  20 20 * * MON-FRI   20 21 * * MON-FRI   30 23 * * MON-FRI   30 0 * * TUE-SAT
//   ※ Cloudflare는 요일 숫자가 1=일요일이라 헷갈리니 영문 요일로 씀
//   뉴욕 16:20 → close (종가·옵션·화면, 약 10분)
//   뉴욕 19:30 → daily (SEC·공매도(18시 공개)·컨센서스 포함 전부)
//
// 필요한 비밀값(Settings → Variables and Secrets, 종류 Secret):
//   GH_TOKEN   깃허브 fine-grained 토큰 (market-data 저장소, Actions: Read and write)
// 선택(실패 시 텔레그램 알림):  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
// 선택(주소로 바로 실행):  RUN_KEY  → https://<worker 주소>/?run=close&key=<RUN_KEY>

const REPO = "flytothejy/market-data";
const WORKFLOW = "hub.yml";

// 뉴욕 현지 시:분 → 보낼 묶음
const SLOTS = { "16:20": "close", "19:30": "daily" };

function nyTime(date) {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", weekday: "short", hourCycle: "h23",
  }).formatToParts(date);
  const g = (t) => p.find((x) => x.type === t).value;
  return { hm: `${g("hour")}:${g("minute")}`, wd: g("weekday") };
}

async function dispatch(env, set) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "tickermap-trigger",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { set } }),
  });
  if (r.status !== 204) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 300)}`);
}

async function alert(env, msg) {
  if (!env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT_ID) return;
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: msg }),
  });
}

export default {
  async scheduled(event, env, ctx) {
    const { hm, wd } = nyTime(new Date(event.scheduledTime));
    const set = SLOTS[hm];
    if (!set || wd === "Sat" || wd === "Sun") {
      console.log(`skip: 뉴욕 ${wd} ${hm} (서머타임 반대편 크론)`);
      return;
    }
    try {
      await dispatch(env, set);
      console.log(`dispatched ${set} (뉴욕 ${wd} ${hm})`);
    } catch (e) {
      console.log(`실패: ${e.message}`);
      ctx.waitUntil(alert(env, `티커맵 깨우미 실패 (${set}): ${e.message}`));
      throw e;
    }
  },

  // 주소로 들어오면 상태만 보여줌. ?run=close|daily&key=<RUN_KEY 비밀값> 이면 지금 바로 실행 (시험·수동용)
  async fetch(req, env) {
    const u = new URL(req.url), run = u.searchParams.get("run");
    if (run) {
      if (!env.RUN_KEY || u.searchParams.get("key") !== env.RUN_KEY) return new Response("key가 맞지 않아요\n", { status: 403 });
      if (!["close", "daily", "weekly"].includes(run)) return new Response("run은 close · daily · weekly 중 하나\n", { status: 400 });
      try {
        await dispatch(env, run);
        return new Response(`실행 요청 보냄: ${run} (GitHub Actions에서 확인)\n`, { headers: { "content-type": "text/plain; charset=utf-8" } });
      } catch (e) {
        return new Response(`실패: ${e.message}\n`, { status: 502, headers: { "content-type": "text/plain; charset=utf-8" } });
      }
    }
    const { hm, wd } = nyTime(new Date());
    return new Response(`tickermap trigger — 뉴욕 지금 ${wd} ${hm}\n예약: ${Object.entries(SLOTS).map(([k, v]) => `${k} ${v}`).join(", ")}\n토큰: ${env.GH_TOKEN ? "있음" : "없음"}\n`, {
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  },
};
