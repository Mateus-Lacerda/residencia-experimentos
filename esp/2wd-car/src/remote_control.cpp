#include "common.h"
#include <WebServer.h>
#include <WiFi.h>

const char *AP_SSID = "carrinho-residencia";
const char *AP_PASSWORD = "residencia123";

WebServer server(80);

const char *CONTROL_PAGE = R"html(
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Controle do carrinho</title>
<style>
  html, body {
    height: 100%;
    margin: 0;
    background: #111;
    color: #eee;
    font-family: sans-serif;
    overscroll-behavior: none;
    touch-action: none;
  }
  .pad {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: 1fr 1fr 1fr;
    gap: 12px;
    height: 100vh;
    padding: 12px;
    box-sizing: border-box;
  }
  button {
    font-size: 1.5rem;
    border: none;
    border-radius: 12px;
    background: #333;
    color: #eee;
  }
  button:active {
    background: #555;
  }
  #fwd { grid-column: 2; grid-row: 1; }
  #left { grid-column: 1; grid-row: 2; }
  #stop { grid-column: 2; grid-row: 2; background: #611; }
  #right { grid-column: 3; grid-row: 2; }
  #back { grid-column: 2; grid-row: 3; }
</style>
</head>
<body>
<div class="pad">
  <button id="fwd">frente</button>
  <button id="left">esquerda</button>
  <button id="stop">parar</button>
  <button id="right">direita</button>
  <button id="back">tras</button>
</div>
<script>
  function send(path) {
    fetch(path).catch(() => {});
  }

  function bind(id, path) {
    const el = document.getElementById(id);
    const start = (e) => { e.preventDefault(); send(path); };
    const end = (e) => { e.preventDefault(); send('/stop'); };
    el.addEventListener('touchstart', start);
    el.addEventListener('touchend', end);
    el.addEventListener('mousedown', start);
    el.addEventListener('mouseup', end);
  }

  bind('fwd', '/fwd');
  bind('back', '/back');
  bind('left', '/left');
  bind('right', '/right');

  document.getElementById('stop').addEventListener('click', () => send('/stop'));
</script>
</body>
</html>
)html";

void setup() {
  Serial.begin(115200);

  setupMotors();
  setupEncoders();

  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  server.on("/", []() { server.send(200, "text/html", CONTROL_PAGE); });
  server.on("/fwd", []() { driveForward(); server.send(200, "text/plain", "OK"); });
  server.on("/back", []() { driveBackward(); server.send(200, "text/plain", "OK"); });
  server.on("/left", []() { turnLeft(); server.send(200, "text/plain", "OK"); });
  server.on("/right", []() { turnRight(); server.send(200, "text/plain", "OK"); });
  server.on("/stop", []() { stopMotors(); server.send(200, "text/plain", "OK"); });
  server.begin();
}

void loop() {
  server.handleClient();
}
