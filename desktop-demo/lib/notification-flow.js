function createNotificationFlow({ request, openExternal, wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), maxPolls = 300 }) {
  let active = null;
  async function performConnect() {
    const started = await request({ method: "POST", requestPath: "/notification-connections/kakao/authorize" });
    await openExternal(started.authorization_url);
    for (let attempt = 0; attempt < maxPolls; attempt += 1) {
      await wait(1000);
      const status = await request({ requestPath: "/notification-connections/kakao" });
      if (status.connected) return status;
    }
    throw new Error("알림 연결 시간이 만료되었습니다. 다시 시도해 주세요.");
  }
  function connect() {
    if (active) return active;
    active = performConnect().finally(() => { active = null; });
    return active;
  }
  const status = () => request({ requestPath: "/notification-connections/kakao" });
  async function disconnect() {
    await request({ method: "DELETE", requestPath: "/notification-connections/kakao" });
    return { connected: false };
  }
  return { connect, status, disconnect };
}
module.exports = { createNotificationFlow };
