const test = require("node:test");
const assert = require("node:assert/strict");
const { createNotificationFlow } = require("../lib/notification-flow");

test("notification connection opens consent and polls until connected", async () => {
  const paths=[]; const opened=[];
  const request=async ({ method="GET", requestPath }) => {
    paths.push(`${method} ${requestPath}`);
    if (requestPath.endsWith("authorize")) return { authorization_url:"https://kauth.example/consent" };
    return { connected: paths.filter((item) => item.startsWith("GET")).length > 1 };
  };
  const flow=createNotificationFlow({ request, openExternal: async (url) => opened.push(url), wait: async () => {}, maxPolls:3 });

  const result=await flow.connect();

  assert.equal(result.connected, true);
  assert.deepEqual(opened, ["https://kauth.example/consent"]);
});
