/*
 * Cena isométrica em pixel art do Escritório Virtual.
 * Tudo é desenhado por código (formas e sprites próprios), sem imagens externas.
 * A cena só LÊ o estado fornecido pelo app; não grava nada e não acessa rede ou disco.
 */
(function () {
  "use strict";
  const EV = (window.EV = window.EV || {});

  // ================================================================ geometria
  const ML = 14;          // meia largura do ladrilho (px lógicos)
  const MA = 7;           // meia altura do ladrilho
  const PAREDE = 62;      // altura das paredes
  const ESP = 0.35;       // espessura das paredes (ladrilhos)
  const MARGEM = 10;
  const SALA_X = 20;
  const SALA_Y = 13;

  const OX = Math.ceil((SALA_Y + ESP) * ML) + MARGEM;
  const OY = PAREDE + Math.ceil(2 * ESP * MA) + MARGEM;
  const LARGURA = Math.ceil((SALA_X + SALA_Y + 2 * ESP) * ML) + 2 * MARGEM;
  const ALTURA = OY + (SALA_X + SALA_Y) * MA + MARGEM;

  const iso = (x, y, z = 0) => [OX + (x - y) * ML, OY + (x + y) * MA - z];

  // ================================================================ cores
  function rgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
  }
  function hex(c) {
    return "#" + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
  }
  function misturar(a, b, t) {
    const A = rgb(a);
    const B = rgb(b);
    return hex(A.map((v, i) => v + (B[i] - v) * t));
  }
  const clarear = (c, t) => misturar(c, "#ffffff", t);
  const escurecer = (c, t) => misturar(c, "#000000", t);
  const tons = (base) => ({ topo: clarear(base, 0.14), esq: base, dir: escurecer(base, 0.16) });

  const COR = {
    contorno: "#1b1d22",
    paredeFundo: "#e6dccb",
    paredeEsq: "#d6cbb7",
    lambriFundo: "#b8a487",
    lambriEsq: "#a8957a",
    frisoClaro: "#f1e8d7",
    rodape: "#5f574c",
    topoParede: "#7b7264",
    pontaParedeX: "#958b7a",
    pontaParedeY: "#aea48f",
    madeiraA: "#c3976a",
    madeiraB: "#bb9065",
    nogueiraA: "#8e6b4f",
    nogueiraB: "#87654a",
    carpeteA: "#46636f",
    carpeteB: "#42606b",
    carpeteBorda: "#33505b",
    quenteA: "#7d6954",
    quenteB: "#786450",
    tampo: tons("#d3cbbd"),
    perna: tons("#5a5751"),
    nogueira: tons("#5e4331"),
    couroVerde: tons("#3d5a48"),
    monitor: tons("#2c3038"),
    teclado: tons("#9da3ab"),
    papel: { topo: "#f6f3ec", esq: "#d8d3c8", dir: "#c6c1b6" },
    cinzaArquivo: tons("#8e969f"),
    madeiraEstante: tons("#6b4c35"),
    caixaArquivo: tons("#c4a06c"),
    divisoria: tons("#5d7088"),
    vaso: tons("#b0603f"),
    sofa: tons("#4f6884"),
    almofada: tons("#5f7a98"),
    bancada: tons("#cfc6b6"),
    maquina: tons("#33373d"),
    branco: tons("#e3e7ea"),
    agua: tons("#8cc4e0"),
    cadeira: tons("#2e3846"),
    cadeiraClara: tons("#3d4a5c"),
    metal: tons("#6d737c"),
    ouro: tons("#c99a3c"),
    folhas: ["#3f8a55", "#2e6e43", "#56a56d", "#2a5f3b"],
    selecao: "#f0b74a"
  };

  // ================================================================ primitivas
  function poligono(ctx, pts, cor) {
    ctx.fillStyle = cor;
    ctx.beginPath();
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(Math.round(x), Math.round(y)) : ctx.moveTo(Math.round(x), Math.round(y))));
    ctx.closePath();
    ctx.fill();
  }

  function linha(ctx, a, b, cor) {
    ctx.strokeStyle = cor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(a[0]) + 0.5, Math.round(a[1]) + 0.5);
    ctx.lineTo(Math.round(b[0]) + 0.5, Math.round(b[1]) + 0.5);
    ctx.stroke();
  }

  function pixel(ctx, x, y, cor) {
    ctx.fillStyle = cor;
    ctx.fillRect(Math.round(x), Math.round(y), 1, 1);
  }

  // Disco em pixels (sem antisserrilhado), opcionalmente achatado na vertical.
  function bolha(ctx, cx, cy, r, cor, achatar = 1) {
    ctx.fillStyle = cor;
    for (let dy = -r; dy <= r; dy++) {
      const w = Math.floor(Math.sqrt(r * r - dy * dy));
      ctx.fillRect(Math.round(cx - w), Math.round(cy + dy * achatar), 2 * w + 1, Math.max(1, Math.ceil(achatar)));
    }
  }

  // Caixa isométrica: (x, y, z) canto de trás; w ao longo de x, d ao longo de y, h em px.
  function caixa(ctx, x, y, z, w, d, h, c, arestas = true) {
    poligono(ctx, [iso(x, y + d, z), iso(x + w, y + d, z), iso(x + w, y + d, z + h), iso(x, y + d, z + h)], c.esq);
    poligono(ctx, [iso(x + w, y, z), iso(x + w, y + d, z), iso(x + w, y + d, z + h), iso(x + w, y, z + h)], c.dir);
    poligono(ctx, [iso(x, y, z + h), iso(x + w, y, z + h), iso(x + w, y + d, z + h), iso(x, y + d, z + h)], c.topo);
    if (arestas && h >= 3 && w >= 0.3 && d >= 0.3) {
      const claro = clarear(c.topo, 0.3);
      linha(ctx, iso(x, y + d, z + h), iso(x + w, y + d, z + h), claro);
      linha(ctx, iso(x + w, y, z + h), iso(x + w, y + d, z + h), claro);
      linha(ctx, iso(x + w, y + d, z), iso(x + w, y + d, z + h), escurecer(c.esq, 0.22));
    }
  }

  // Retângulos sobre planos verticais: plano y constante (frente) e plano x constante (lateral).
  function faceY(ctx, y, x0, x1, z0, z1, cor) {
    poligono(ctx, [iso(x0, y, z0), iso(x1, y, z0), iso(x1, y, z1), iso(x0, y, z1)], cor);
  }
  function faceX(ctx, x, y0, y1, z0, z1, cor) {
    poligono(ctx, [iso(x, y0, z0), iso(x, y1, z0), iso(x, y1, z1), iso(x, y0, z1)], cor);
  }
  // Retângulo deitado (sobre um tampo na altura z).
  function faceZ(ctx, x0, y0, x1, y1, z, cor) {
    poligono(ctx, [iso(x0, y0, z), iso(x1, y0, z), iso(x1, y1, z), iso(x0, y1, z)], cor);
  }

  function brilho(ctx, x, y, raio, cor, alfa) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, raio);
    g.addColorStop(0, cor.replace("A", String(alfa)));
    g.addColorStop(1, cor.replace("A", "0"));
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = g;
    ctx.fillRect(x - raio, y - raio, raio * 2, raio * 2);
    ctx.restore();
  }

  // ================================================================ sprites (14 x 22)
  // o contorno · h/H cabelo/brilho · s/S pele/sombra · e olhos · c/C roupa/sombra
  // w gola · t gravata · p calça · K/k/j cadeira (escuro/médio/brilho) · m metal · "." vazio
  const SPRITE_COSTAS = [
    ".....oooo.....",
    "....ohhhho....",
    "...ohhHhhho...",
    "...ohHhhhho...",
    "...ohhhhhho...",
    "..sohhhhhhos..",
    "...ohhhhhho...",
    "....ohhhho....",
    ".....oSSo.....",
    "..oCccccccCo..",
    ".oCccccccccCo.",
    ".oCccccccccCo.",
    "oKKKKKKKKKKKKo",
    "oKkkkkkkkkkkKo",
    "oKkjjjjjjjjkKo",
    "oKkkkkkkkkkkKo",
    "oKkkkkkkkkkkKo",
    ".oKKKKKKKKKKo.",
    ".....ommo.....",
    "....ommmmo....",
    "..ommmmmmmmo..",
    "..o.o....o.o.."
  ];
  const LINHA_CADEIRA = 12;

  const SPRITE_FRENTE = [
    ".....oooo.....",
    "....ohhhho....",
    "...ohhHhhho...",
    "...ohhhhhho...",
    "...ohssssho...",
    "...oesssseo...",
    "..SossssssoS..",
    "...osssssso...",
    "....osSSso....",
    ".....oSSo.....",
    "..occwwwwcco..",
    ".occcwttwccco.",
    ".occcCttCccco.",
    ".occccttcccco.",
    ".osccccccccso.",
    ".occcccccccco.",
    ".occcccccccco.",
    ".oppppppppppo.",
    ".oppppppppppo.",
    "..oppppppppo..",
    "..oppo..oppo..",
    "..oooo..oooo.."
  ];

  // Em pé, de costas (andando para o fundo da sala ou parado diante do Coordenador).
  const SPRITE_PE_COSTAS = SPRITE_COSTAS.slice(0, 12).concat([
    ".oCccccccccCo.",
    ".occcccccccco.",
    ".occcccccccco.",
    ".osccccccccso.",
    ".occcccccccco.",
    ".oppppppppppo.",
    ".oppppppppppo.",
    "..oppppppppo..",
    "..oppo..oppo..",
    "..oooo..oooo.."
  ]);
  // Passo: as duas últimas linhas alternam enquanto o personagem anda.
  const PERNAS_PASSO = [".oppo....oppo.", ".oooo....oooo."];
  // Sentado no sofá/poltrona da copa (de frente): tronco do sprite de frente + pernas dobradas.
  const SPRITE_SENTADO = SPRITE_FRENTE.slice(0, 17).concat([".oppppppppppo.", ".oppppppppppo.", "..oooo..oooo.."]);

  // Detalhes que diferenciam os personagens (coluna, linha, chave da paleta).
  const DETALHES = {
    documentos: [[6, 8, "h"], [7, 8, "h"], [6, 9, "h"], [7, 9, "H"], [6, 10, "h"], [7, 10, "h"]], // rabo de cavalo
    coordenador: [[3, 3, "H"], [10, 3, "H"]],                                                     // têmporas grisalhas
    importacao: [[5, 0, "h"], [6, 0, "H"], [7, 0, "h"], [8, 0, "h"]]                               // coque
  };

  const GLIFOS = {
    LIVRE: [".x.x...", "..x.x..", ".......", "xxxxx..", "xxxxx.x", "xxxxxx.", ".xxx..."],
    TRABALHANDO: ["..x.x..", ".xxxxx.", "xx...xx", ".x...x.", "xx...xx", ".xxxxx.", "..x.x.."],
    AGUARDANDO_SUPERVISOR: ["xxxxxxx", ".x...x.", "..x.x..", "...x...", "..x.x..", ".xxxxx.", "xxxxxxx"],
    PENDENCIA: ["...x...", "...x...", "...x...", "...x...", "...x...", ".......", "...x..."],
    CONCLUIDO: [".......", "......x", ".....x.", "x...x..", ".x.x...", "..x....", "......."],
    ERRO: ["x.....x", ".x...x.", "..x.x..", "...x...", "..x.x..", ".x...x.", "x.....x"],
    OFFLINE: ["xxxx...", "...x...", "..x....", "xxxx...", "....xxx", ".....x.", "....xxx"],
    NAO_IMPLEMENTADO: [".......", ".......", ".......", "x..x..x", ".......", ".......", "......."]
  };

  const BALAO = {
    LIVRE: { fundo: "#f4f1ea", glifo: "#3f8a60" },
    TRABALHANDO: { fundo: "#e8f1fa", glifo: "#2f6fa8" },
    AGUARDANDO_SUPERVISOR: { fundo: "#f6d9a6", glifo: "#6b4310" },
    PENDENCIA: { fundo: "#f2d45c", glifo: "#2a2410" },
    CONCLUIDO: { fundo: "#bfe9cf", glifo: "#1e6b40" },
    ERRO: { fundo: "#e25d5d", glifo: "#ffffff" },
    OFFLINE: { fundo: "#c9cdd3", glifo: "#4a515b" },
    NAO_IMPLEMENTADO: { fundo: "#d9d4ea", glifo: "#5a4f86" }
  };

  const PALETA_BASE = {
    o: "#1b1d22", e: "#1b1d22", w: "#efebe3", p: "#2b2f36",
    K: "#232a35", k: "#323c4a", j: "#45526a", m: "#5d636c"
  };

  const APARENCIA = {
    coordenador: { h: "#3a2b22", H: "#8d8780", s: "#e2b58d", S: "#c4936d", c: "#26405e", C: "#1b2f47", t: "#c99a3c" },
    documentos: { h: "#2a1d18", H: "#4a352b", s: "#c98e62", S: "#a8734d", c: "#2f8f83", C: "#226c63", t: "#2f8f83" },
    fiscal: { h: "#4a3326", H: "#6a4a38", s: "#d7a67b", S: "#b98a62", c: "#8a5a3c", C: "#6b452e", t: "#8a5a3c" },
    dp: { h: "#2a2421", H: "#463c37", s: "#b77f55", S: "#996542", c: "#6b5b8f", C: "#52456f", t: "#6b5b8f" },
    financeiro: { h: "#1f1a17", H: "#3a302a", s: "#c9966b", S: "#a87a52", c: "#7a3b3b", C: "#5e2c2c", t: "#7a3b3b" },
    importacao: { h: "#6b3e26", H: "#8f5a3a", s: "#e0b089", S: "#c29069", c: "#2f4f7a", C: "#233c5e", t: "#c99a3c" },
    bancos: { h: "#3b2f2a", H: "#5a4840", s: "#d9a77f", S: "#ba8a63", c: "#3f6b4a", C: "#2f5238", t: "#3f6b4a" },
    conciliacao: { h: "#5a3b22", H: "#7a5434", s: "#e3bb94", S: "#c69c74", c: "#3f6b4a", C: "#2f5238", t: "#3f6b4a" }
  };

  function cinza(h) {
    const [r, g, b] = rgb(h);
    const l = Math.round((0.3 * r + 0.59 * g + 0.11 * b) * 0.7 + 45);
    return hex([l, l, l + 4]);
  }

  function paletaDe(id, status) {
    const p = Object.assign({}, PALETA_BASE, APARENCIA[id] || APARENCIA.documentos);
    if (status === "OFFLINE") for (const k of Object.keys(p)) p[k] = cinza(p[k]);
    return p;
  }

  // Escala dos personagens em relação à mobília (protagonistas da cena).
  const ESC_PESSOA = 1.25;

  // Pixel de sprite ampliado: cada célula vira um retângulo inteiro (vizinho mais próximo).
  function celula(ctx, sx, sy, c, r, cor, e = ESC_PESSOA) {
    const x0 = Math.round(sx + c * e);
    const y0 = Math.round(sy + r * e);
    ctx.fillStyle = cor;
    ctx.fillRect(x0, y0, Math.round(sx + (c + 1) * e) - x0, Math.round(sy + (r + 1) * e) - y0);
  }

  function desenharSprite(ctx, linhas, paleta, sx, sy, opcoes = {}) {
    const { de = 0, ate = linhas.length, corUnica = null, deslocarAte = 0, deslocamento = 0 } = opcoes;
    for (let r = de; r < ate; r++) {
      const dy = r < deslocarAte ? deslocamento : 0;
      const l = linhas[r];
      for (let c = 0; c < l.length; c++) {
        const ch = l[c];
        if (ch === ".") continue;
        celula(ctx, sx, sy, c, r + dy, corUnica || paleta[ch] || "#ff00ff");
      }
    }
  }

  // Canto superior esquerdo do sprite a partir do ponto do personagem no piso.
  const origemSprite = (ax, ay) => [Math.round(ax - 7 * ESC_PESSOA), Math.round(ay - 22 * ESC_PESSOA)];
  const TOPO_CABECA = Math.round(22 * ESC_PESSOA);

  // ================================================================ fonte pixel 3x5 (placas)
  const FONTE = {
    A: [".x.", "x.x", "xxx", "x.x", "x.x"], B: ["xx.", "x.x", "xx.", "x.x", "xx."],
    C: [".xx", "x..", "x..", "x..", ".xx"], D: ["xx.", "x.x", "x.x", "x.x", "xx."],
    E: ["xxx", "x..", "xx.", "x..", "xxx"], F: ["xxx", "x..", "xx.", "x..", "x.."],
    G: [".xx", "x..", "x.x", "x.x", ".xx"], I: ["xxx", ".x.", ".x.", ".x.", "xxx"],
    L: ["x..", "x..", "x..", "x..", "xxx"], M: ["x...x", "xx.xx", "x.x.x", "x...x", "x...x"],
    N: ["xx.", "x.x", "x.x", "x.x", "x.x"], O: [".x.", "x.x", "x.x", "x.x", ".x."],
    P: ["xx.", "x.x", "xx.", "x..", "x.."], R: ["xx.", "x.x", "xx.", "x.x", "x.x"],
    S: [".xx", "x..", ".x.", "..x", "xx."], T: ["xxx", ".x.", ".x.", ".x.", ".x."],
    U: ["x.x", "x.x", "x.x", "x.x", "xxx"], V: ["x.x", "x.x", "x.x", "x.x", ".x."],
    X: ["x.x", "x.x", ".x.", "x.x", "x.x"], "·": ["...", "...", ".x.", "...", "..."],
    "+": ["...", ".x.", "xxx", ".x.", "..."], " ": ["...", "...", "...", "...", "..."]
  };
  const normalizar = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
  const glifo = (ch) => FONTE[ch] || FONTE[" "];
  const larguraTexto = (s) => [...normalizar(s)].reduce((t, ch) => t + glifo(ch)[0].length + 1, 0) - 1;

  function texto(ctx, s, x, y, cor) {
    ctx.fillStyle = cor;
    let cx = x;
    [...normalizar(s)].forEach((ch) => {
      const g = glifo(ch);
      g.forEach((l, r) => [...l].forEach((v, c) => { if (v === "x") ctx.fillRect(cx + c, y + r, 1, 1); }));
      cx += g[0].length + 1;
    });
  }

  // Plaquinha discreta no piso, em frente a uma estação (linhas centralizadas).
  function placa(ctx, cx, topo, linhas, cores) {
    const l = Math.max(...linhas.map(larguraTexto)) + 6;
    const a = linhas.length * 7 + 3;
    const x = Math.round(cx - l / 2);
    const y = Math.round(topo);
    ctx.fillStyle = "rgba(0, 0, 0, 0.25)";
    ctx.fillRect(x + 1, y + 1, l, a);
    ctx.fillStyle = cores.borda;
    ctx.fillRect(x, y, l, a);
    ctx.fillStyle = cores.fundo;
    ctx.fillRect(x + 1, y + 1, l - 2, a - 2);
    linhas.forEach((s, i) => texto(ctx, s, Math.round(cx - larguraTexto(s) / 2), y + 2 + i * 7, cores.texto[i] || cores.texto[0]));
  }

  // ================================================================ planta do escritório
  // Posição de cada agente (dado visual, separado dos dados operacionais). A posição das mesas NÃO define a ordem
  // de execução: quem distribui as tarefas é sempre o Coordenador.
  //   fileira norte: ① Documentos · ② áreas: Financeiro, Fiscal e DP (lado a lado)
  //   ilha central : ③ Contabilidade (lançamentos): Bancos logo abaixo do Financeiro; Importação VGROW ao lado
  //   faixa sul    : ④ Conciliação (confere os lançamentos propostos; entrega o resultado ao Coordenador ⑤)
  // caminha = personagem funcional que se desloca entre a mesa, o Coordenador e a copa.
  const POSTOS = {
    coordenador: { mesa: { x: 1.5, y: 2.3, w: 3.2, d: 1.3 }, pessoa: { x: 3.05, y: 1.55 }, vista: "frente", etiqueta: 2.3 },
    documentos: { mesa: { x: 7.6, y: 0.45, w: 2.3, d: 1.15 }, pessoa: { x: 8.95, y: 2.0 }, vista: "costas", etiqueta: 0.65, caminha: true },
    financeiro: { mesa: { x: 10.8, y: 0.45, w: 2.3, d: 1.15 }, pessoa: { x: 12.15, y: 2.0 }, vista: "costas", etiqueta: 0.65, caminha: true },
    fiscal: { mesa: { x: 14.0, y: 0.45, w: 2.3, d: 1.15 }, pessoa: { x: 15.35, y: 2.0 }, vista: "costas", etiqueta: 0.65, caminha: true },
    dp: { mesa: { x: 17.2, y: 0.45, w: 2.3, d: 1.15 }, pessoa: { x: 18.55, y: 2.0 }, vista: "costas", etiqueta: 0.65, caminha: true },
    importacao: { mesa: { x: 7.6, y: 6.9, w: 2.3, d: 1.15 }, pessoa: { x: 8.95, y: 8.45 }, vista: "costas", etiqueta: 0.65, caminha: true },
    bancos: { mesa: { x: 10.8, y: 6.9, w: 2.3, d: 1.15 }, pessoa: { x: 12.15, y: 8.45 }, vista: "costas", etiqueta: 0.65, caminha: true },
    conciliacao: { mesa: { x: 15.0, y: 10.75, w: 2.3, d: 1.15 }, pessoa: { x: 16.35, y: 12.3 }, vista: "costas", etiqueta: 0.3, caminha: true }
  };

  // Mesas reservadas para próximos especialistas (hoje nenhuma: a ilha da Contabilidade tem Importação e Bancos).
  const VAGAS = [];

  // Áreas representadas (sem personagem): ilha no piso e âncora do quadro de especialistas.
  const AREAS = {
    contabilidade: { ilha: [7.1, 6.1, 12.9, 9.9], quadro: { x: 9.4, y: 10.4 } }
  };

  // Ponto em frente à mesa do Coordenador onde os agentes buscam e entregam o trabalho.
  const VISITA_COORDENADOR = { x: 4.15, y: 4.55 };
  // Onde quem entrega a pasta para, ao lado da mesa de quem recebe (passagem entre áreas, sem voltar ao Coordenador).
  const ENTREGA = { coordenador: VISITA_COORDENADOR, financeiro: { x: 10.95, y: 2.55 }, fiscal: { x: 14.15, y: 2.55 }, dp: { x: 17.35, y: 2.55 },
                    bancos: { x: 11.05, y: 9.0 }, conciliacao: { x: 14.6, y: 11.3 } };

  // Placas fixas: na fileira norte, acima da parede (nunca cobrem personagens ou móveis); na ilha e na faixa sul, no piso.
  // A numeração mostra a sequência do trabalho; a posição das mesas não define ordem de execução (quem distribui é o Coordenador).
  const PLACAS = {
    coordenador: { texto: "5 · Coordenador", parede: 3.1 },
    documentos: { texto: "1 · Documentos", parede: 8.75 },
    financeiro: { texto: "2 · Financeiro", parede: 11.95 },
    fiscal: { texto: "2 · Fiscal", parede: 15.15 },
    dp: { texto: "2 · DP", parede: 18.35 },
    conciliacao: { texto: "4 · Conciliação", piso: { x: 15.6, y: 12.95 }, esquerda: true },
    copa: { texto: "Copa", paredeEsq: 9.6, copa: true }
  };

  // Copa: 3 lugares no sofá e 1 na poltrona; quem sobrar fica em pé perto do bebedouro.
  // chave = ordem de desenho logo depois do móvel; z = altura do assento.
  const COPA = {
    assentos: [
      { x: 1.0, y: 8.76, z: 6, chave: 10.21 },
      { x: 1.0, y: 9.71, z: 6, chave: 10.22 },
      { x: 1.0, y: 10.66, z: 6, chave: 10.23 },
      { x: 4.45, y: 9.65, z: 6, chave: 13.95 }
    ],
    emPe: [{ x: 3.0, y: 7.45 }, { x: 3.7, y: 7.55 }, { x: 2.4, y: 11.35 }]
  };

  // ================================================================ caminhos (grade sobre a planta)
  const CELULA = 0.25;
  const FOLGA = 0.22;                       // raio do personagem: distância mínima de móveis e paredes
  const NX = Math.round(SALA_X / CELULA);
  const NY = Math.round(SALA_Y / CELULA);

  // Grade de células livres a partir das áreas ocupadas (móveis, mesas e divisórias).
  function criarGrade(retangulos) {
    const livre = new Uint8Array(NX * NY);
    for (let j = 0; j < NY; j++) {
      for (let i = 0; i < NX; i++) {
        const cx = (i + 0.5) * CELULA;
        const cy = (j + 0.5) * CELULA;
        const parede = cx < 0.3 || cy < 0.3 || cx > SALA_X - 0.3 || cy > SALA_Y - 0.3;
        const ocupado = retangulos.some(([x, y, w, d]) => cx > x - FOLGA && cx < x + w + FOLGA && cy > y - FOLGA && cy < y + d + FOLGA);
        livre[j * NX + i] = parede || ocupado ? 0 : 1;
      }
    }
    return { livre, retangulos };
  }

  const celulaDe = (p) => [Math.min(NX - 1, Math.max(0, Math.floor(p.x / CELULA))), Math.min(NY - 1, Math.max(0, Math.floor(p.y / CELULA)))];
  const centro = (i, j) => ({ x: (i + 0.5) * CELULA, y: (j + 0.5) * CELULA });
  const ehLivre = (g, i, j) => i >= 0 && j >= 0 && i < NX && j < NY && g.livre[j * NX + i] === 1;

  // Célula livre mais próxima (o assento do sofá e a cadeira ficam "dentro" do móvel).
  function livreMaisProxima(g, p) {
    const [i0, j0] = celulaDe(p);
    if (ehLivre(g, i0, j0)) return [i0, j0];
    let melhor = null;
    for (let r = 1; r < 12 && !melhor; r++) {
      for (let j = j0 - r; j <= j0 + r; j++) {
        for (let i = i0 - r; i <= i0 + r; i++) {
          if (!ehLivre(g, i, j)) continue;
          const c = centro(i, j);
          const dist = Math.hypot(c.x - p.x, c.y - p.y);
          if (!melhor || dist < melhor[2]) melhor = [i, j, dist];
        }
      }
    }
    return melhor ? [melhor[0], melhor[1]] : [i0, j0];
  }

  // Linha livre entre dois pontos: percorre TODAS as células tocadas pelo segmento (sem amostragem), inclusive
  // as duas vizinhas quando ele passa exatamente por uma quina.
  function visivel(g, a, b) {
    let [i, j] = celulaDe(a);
    const [ti, tj] = celulaDe(b);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const si = Math.sign(dx);
    const sj = Math.sign(dy);
    const passoX = dx ? CELULA / Math.abs(dx) : Infinity;
    const passoY = dy ? CELULA / Math.abs(dy) : Infinity;
    let proxX = dx ? (si > 0 ? (i + 1) * CELULA - a.x : a.x - i * CELULA) / Math.abs(dx) : Infinity;
    let proxY = dy ? (sj > 0 ? (j + 1) * CELULA - a.y : a.y - j * CELULA) / Math.abs(dy) : Infinity;
    for (let n = 0; n < NX + NY + 4; n++) {
      if (!ehLivre(g, i, j)) return false;
      if (i === ti && j === tj) return true;
      if (Math.abs(proxX - proxY) < 1e-9) {
        if (!ehLivre(g, i + si, j) || !ehLivre(g, i, j + sj)) return false;
        proxX += passoX;
        proxY += passoY;
        i += si;
        j += sj;
      } else if (proxX < proxY) {
        proxX += passoX;
        i += si;
      } else {
        proxY += passoY;
        j += sj;
      }
    }
    return false;
  }

  // A* em 8 direções (sem cortar quinas); depois o caminho é esticado entre pontos que se enxergam.
  // Devolve os pontos de "de" até "para" (o primeiro e o último trecho saem/chegam no assento ou cadeira), ou null.
  function planejarCaminho(g, de, para) {
    const [si, sj] = livreMaisProxima(g, de);
    const [ti, tj] = livreMaisProxima(g, para);
    const inicio = sj * NX + si;
    const fim = tj * NX + ti;
    const custo = new Float64Array(NX * NY).fill(Infinity);
    const veio = new Int32Array(NX * NY).fill(-1);
    const fechado = new Uint8Array(NX * NY);
    const h = (k) => Math.hypot((k % NX) - ti, Math.floor(k / NX) - tj);
    const aberto = [[h(inicio), inicio]];
    custo[inicio] = 0;
    while (aberto.length) {
      let m = 0;
      for (let k = 1; k < aberto.length; k++) if (aberto[k][0] < aberto[m][0]) m = k;
      const atual = aberto.splice(m, 1)[0][1];
      if (atual === fim) break;
      if (fechado[atual]) continue;
      fechado[atual] = 1;
      const ai = atual % NX;
      const aj = Math.floor(atual / NX);
      for (let dj = -1; dj <= 1; dj++) {
        for (let di = -1; di <= 1; di++) {
          if (!di && !dj) continue;
          const ni = ai + di;
          const nj = aj + dj;
          if (!ehLivre(g, ni, nj)) continue;
          if (di && dj && (!ehLivre(g, ai + di, aj) || !ehLivre(g, ai, aj + dj))) continue;
          const k = nj * NX + ni;
          const c = custo[atual] + (di && dj ? Math.SQRT2 : 1);
          if (c < custo[k]) {
            custo[k] = c;
            veio[k] = atual;
            aberto.push([c + h(k), k]);
          }
        }
      }
    }
    if (custo[fim] === Infinity) return null;
    const celulas = [];
    for (let k = fim; k !== -1; k = veio[k]) celulas.unshift(centro(k % NX, Math.floor(k / NX)));
    const esticado = [celulas[0]];
    let ancora = 0;
    for (let k = 2; k < celulas.length; k++) {
      if (!visivel(g, celulas[ancora], celulas[k])) {
        esticado.push(celulas[k - 1]);
        ancora = k - 1;
      }
    }
    if (celulas.length > 1) esticado.push(celulas[celulas.length - 1]);
    return [{ x: de.x, y: de.y }].concat(esticado, [{ x: para.x, y: para.y }])
      .filter((p, k, l) => !k || Math.hypot(p.x - l[k - 1].x, p.y - l[k - 1].y) > 0.01);
  }

  // ================================================================ piso e paredes (camada fixa)
  function zona(x, y) {
    if (x < 6 && y < 6) return "coord";
    if (x >= 13 && y >= 5 && y < 10) return "reuniao";
    if (x < 6 && y >= 7) return "descanso";
    if (x >= 7 && x < 13 && y >= 6 && y < 10) return "contabilidade";
    return "madeira";
  }

  // Percurso da pasta no piso (tracejado discreto com setas): Coordenador → ① → ② → ③ → Coordenador.
  const PERCURSO = [[[5.3, 5.7], [8.6, 3.05]], [[9.4, 3.05], [11.0, 3.05]], [[11.7, 3.4], [11.7, 6.0]], [[10.6, 5.65], [6.2, 5.65]]];

  function desenharPercurso(ctx) {
    const cor = "rgba(240, 183, 74, 0.55)";
    PERCURSO.forEach(([a, b]) => {
      const n = Math.max(2, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.25));
      for (let i = 0; i < n - 1; i += 2) {
        const t0 = i / n;
        const t1 = (i + 1) / n;
        linha(ctx, iso(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0), iso(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1), cor);
      }
      // ponta da seta
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
      const p1 = [b[0] - 0.28 * Math.cos(ang - 0.6), b[1] - 0.28 * Math.sin(ang - 0.6)];
      const p2 = [b[0] - 0.28 * Math.cos(ang + 0.6), b[1] - 0.28 * Math.sin(ang + 0.6)];
      poligono(ctx, [iso(...b), iso(...p1), iso(...p2)], cor);
    });
  }

  // Contorno tracejado da ilha da Contabilidade (lançamentos e especialistas internos).
  function contornoContabilidade(ctx) {
    const [x0, y0, x1, y1] = AREAS.contabilidade.ilha;
    const lados = [[[x0, y0], [x1, y0]], [[x1, y0], [x1, y1]], [[x1, y1], [x0, y1]], [[x0, y1], [x0, y0]]];
    lados.forEach(([a, b]) => {
      const n = Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.3);
      for (let i = 0; i < n; i += 2) {
        const t0 = i / n;
        const t1 = Math.min(1, (i + 1) / n);
        linha(ctx, iso(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0), iso(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1), "rgba(201, 154, 60, 0.8)");
      }
    });
  }

  function ruido(x, y) {
    return ((x * 73856093) ^ (y * 19349663)) % 7 / 100;
  }

  function desenharPiso(ctx) {
    for (let x = 0; x < SALA_X; x++) {
      for (let y = 0; y < SALA_Y; y++) {
        const z = zona(x, y);
        const par = (x + y) % 2 === 0;
        let cor;
        if (z === "coord") cor = par ? COR.nogueiraA : COR.nogueiraB;
        else if (z === "reuniao") {
          const borda = x === 13 || x === SALA_X - 1 || y === 5 || y === 9;
          cor = borda ? COR.carpeteBorda : par ? COR.carpeteA : COR.carpeteB;
        } else if (z === "descanso") cor = par ? COR.quenteA : COR.quenteB;
        else if (z === "contabilidade") cor = par ? "#8f9a86" : "#8a9581";
        else cor = par ? COR.madeiraA : COR.madeiraB;
        cor = escurecer(cor, ruido(x, y));
        poligono(ctx, [iso(x, y), iso(x + 1, y), iso(x + 1, y + 1), iso(x, y + 1)], cor);
        if (z === "madeira" || z === "coord") {
          const junta = escurecer(cor, 0.13);
          linha(ctx, iso(x, y + 0.5), iso(x + 1, y + 0.5), junta);
          linha(ctx, iso(x, y), iso(x + 1, y), escurecer(cor, 0.07));
          const corte = (x * 7 + y * 3) % 2 ? 0.35 : 0.7;
          linha(ctx, iso(x + corte, y), iso(x + corte, y + 0.5), junta);
        }
      }
    }
    contornoContabilidade(ctx);
    desenharPercurso(ctx);
    // tapete da sala do coordenador (borda dourada)
    faceZ(ctx, 1.0, 1.0, 5.4, 5.4, 0, "#a8843a");
    faceZ(ctx, 1.12, 1.12, 5.28, 5.28, 0, "#2f4a63");
    faceZ(ctx, 1.4, 1.4, 5.0, 5.0, 0, "#35536f");
    // tapete da área de descanso
    faceZ(ctx, 1.6, 8.0, 5.2, 12.0, 0, "#7f4535");
    faceZ(ctx, 1.72, 8.12, 5.08, 11.88, 0, "#a35d45");
    for (let i = 0; i < 4; i++) faceZ(ctx, 1.9, 8.5 + i * 0.9, 4.9, 8.62 + i * 0.9, 0, "#c47b5c");
    // sombra de contato junto às paredes
    poligono(ctx, [iso(0, 0), iso(SALA_X, 0), iso(SALA_X, 0.3), iso(0.3, 0.3)], "rgba(40, 25, 10, 0.16)");
    poligono(ctx, [iso(0, 0), iso(0.3, 0.3), iso(0.3, SALA_Y), iso(0, SALA_Y)], "rgba(40, 25, 10, 0.16)");
  }

  function janela(ctx, eixo, a0, a1, z0, z1, noite) {
    const face = eixo === "y" ? (b0, b1, c0, c1, cor) => faceY(ctx, 0, b0, b1, c0, c1, cor)
      : (b0, b1, c0, c1, cor) => faceX(ctx, 0, b0, b1, c0, c1, cor);
    face(a0, a1, z0, z1, "#4c5560");
    face(a0 + 0.08, a1 - 0.08, z0 + 2, z1 - 2, noite ? "#1a2638" : "#9cc6dc");
    face(a0 + 0.08, a1 - 0.08, z1 - 12, z1 - 2, noite ? "#202f45" : "#bcdbea");
    // persiana parcialmente baixada
    for (let z = z1 - 3; z > z1 - 10; z -= 2) face(a0 + 0.08, a1 - 0.08, z, z + 1, noite ? "#2c3540" : "#dcd6c8");
    face(a0 + 0.2, a0 + 0.42, z0 + 6, z1 - 12, noite ? "#26364e" : "#d6ecf6");
    const meio = (a0 + a1) / 2;
    face(meio - 0.04, meio + 0.04, z0 + 2, z1 - 2, "#4c5560");
    face(a0 + 0.08, a1 - 0.08, (z0 + z1) / 2 - 0.5, (z0 + z1) / 2 + 0.5, "#4c5560");
    // peitoril
    if (eixo === "y") caixa(ctx, a0 - 0.06, 0, z0 - 2, a1 - a0 + 0.12, 0.16, 2, tons("#e9e2d4"), false);
    else caixa(ctx, 0, a0 - 0.06, z0 - 2, 0.16, a1 - a0 + 0.12, 2, tons("#e9e2d4"), false);
  }

  function luzJanela(ctx, eixo, a0, a1) {
    const cor = "rgba(255, 236, 190, 0.13)";
    if (eixo === "y") poligono(ctx, [iso(a0 + 0.1, 0.1), iso(a1 - 0.1, 0.1), iso(a1 + 0.6, 2.6), iso(a0 + 0.7, 2.6)], cor);
    else poligono(ctx, [iso(0.1, a0 + 0.1), iso(0.1, a1 - 0.1), iso(2.6, a1 + 0.6), iso(2.6, a0 + 0.7)], cor);
  }

  function desenharParedes(ctx, noite) {
    // faces internas
    faceY(ctx, 0, 0, SALA_X, 0, PAREDE, COR.paredeFundo);
    faceX(ctx, 0, 0, SALA_Y, 0, PAREDE, COR.paredeEsq);
    // lambri, friso e rodapé
    faceY(ctx, 0, 0, SALA_X, 0, 20, COR.lambriFundo);
    faceX(ctx, 0, 0, SALA_Y, 0, 20, COR.lambriEsq);
    for (let x = 1; x < SALA_X; x++) linha(ctx, iso(x, 0, 3), iso(x, 0, 19), escurecer(COR.lambriFundo, 0.08));
    for (let y = 1; y < SALA_Y; y++) linha(ctx, iso(0, y, 3), iso(0, y, 19), escurecer(COR.lambriEsq, 0.08));
    faceY(ctx, 0, 0, SALA_X, 19, 21, COR.frisoClaro);
    faceX(ctx, 0, 0, SALA_Y, 19, 21, clarear(COR.lambriEsq, 0.45));
    faceY(ctx, 0, 0, SALA_X, 0, 3, COR.rodape);
    faceX(ctx, 0, 0, SALA_Y, 0, 3, escurecer(COR.rodape, 0.1));
    // canto entre as paredes
    linha(ctx, iso(0, 0, 0), iso(0, 0, PAREDE), escurecer(COR.paredeEsq, 0.18));
    // espessura (topo e pontas)
    poligono(ctx, [iso(0, 0, PAREDE), iso(SALA_X, 0, PAREDE), iso(SALA_X, -ESP, PAREDE), iso(-ESP, -ESP, PAREDE), iso(-ESP, SALA_Y, PAREDE), iso(0, SALA_Y, PAREDE)], COR.topoParede);
    faceX(ctx, SALA_X, -ESP, 0, 0, PAREDE, COR.pontaParedeX);
    faceY(ctx, SALA_Y, -ESP, 0, 0, PAREDE, COR.pontaParedeY);
    linha(ctx, iso(0, 0, PAREDE), iso(SALA_X, 0, PAREDE), clarear(COR.topoParede, 0.25));
    linha(ctx, iso(0, 0, PAREDE), iso(0, SALA_Y, PAREDE), clarear(COR.topoParede, 0.25));

    // janelas
    [7.75, 10.95, 14.15, 17.35].forEach((x) => janela(ctx, "y", x, x + 2.0, 28, 54, noite));
    janela(ctx, "y", 1.0, 2.8, 28, 54, noite);
    janela(ctx, "x", 8.2, 10.6, 28, 54, noite);

    // sala do coordenador: quadro com o emblema e certificado
    faceX(ctx, 0, 1.4, 4.2, 28, 50, "#2b3a4c");
    faceX(ctx, 0, 1.5, 4.1, 29, 49, "#34475d");
    faceX(ctx, 0, 2.45, 3.15, 32, 46, "#c99a3c");
    faceX(ctx, 0, 2.62, 2.98, 35, 43, "#34475d");
    faceX(ctx, 0, 4.6, 5.5, 34, 46, "#6b4c35");
    faceX(ctx, 0, 4.68, 5.42, 35, 45, "#f2ede2");
    for (let z = 37; z < 44; z += 2) faceX(ctx, 0, 4.8, 5.3, z, z + 1, "#b9b2a4");
    // quadro de metas e calendário na parede do fundo
    faceY(ctx, 0, 9.85, 10.85, 30, 48, "#f2ede2");
    faceY(ctx, 0, 9.85, 10.85, 46, 48, "#b0473a");
    for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) faceY(ctx, 0, 9.95 + i * 0.22, 10.12 + i * 0.22, 33 + j * 4, 35 + j * 4, "#cfc7b6");
    faceY(ctx, 0, 13.05, 14.05, 30, 48, "#2f3a46");
    [[0.1, 6], [0.32, 10], [0.54, 8], [0.76, 13]].forEach(([dx, h]) => faceY(ctx, 0, 13.1 + dx, 13.26 + dx, 33, 33 + h, "#f0b74a"));
    // mural de recados (descanso)
    faceX(ctx, 0, 11.0, 12.6, 30, 46, "#a07a52");
    faceX(ctx, 0, 11.08, 12.52, 31, 45, "#c49a6a");
    [[11.2, 39, "#f2d45c"], [11.7, 41, "#9ccdf0"], [12.1, 36, "#f6b5a8"], [11.4, 33, "#bfe9cf"]].forEach(([y, z, c]) => faceX(ctx, 0, y, y + 0.32, z, z + 4, c));
    // placa da área de reunião
    faceY(ctx, 0, 16.3, 17.2, 44, 50, "#2b3a4c");
  }

  function relogioParede(ctx, agora) {
    const cx = 6.75;
    const cz = 47;
    faceY(ctx, 0, cx - 0.42, cx + 0.42, cz - 6, cz + 6, "#3a3f47");
    faceY(ctx, 0, cx - 0.34, cx + 0.34, cz - 5, cz + 5, "#f6f3ec");
    const h = (agora.getHours() % 12) + agora.getMinutes() / 60;
    const m = agora.getMinutes();
    const ponta = (ang, r, rz) => iso(cx + r * Math.sin(ang), 0, cz + rz * Math.cos(ang));
    linha(ctx, iso(cx, 0, cz), ponta((h / 12) * 2 * Math.PI, 0.16, 2.6), "#1b1d22");
    linha(ctx, iso(cx, 0, cz), ponta((m / 60) * 2 * Math.PI, 0.26, 4), "#b0473a");
  }

  // ================================================================ objetos
  function mesaTrabalho(ctx, m) {
    caixa(ctx, m.x + 0.04, m.y + 0.06, 0, 0.12, m.d - 0.12, 9, COR.perna);
    caixa(ctx, m.x + m.w - 0.16, m.y + 0.06, 0, 0.12, m.d - 0.12, 9, COR.perna);
    caixa(ctx, m.x + 0.16, m.y + 0.06, 3, m.w - 0.32, 0.06, 6, COR.perna, false);
    caixa(ctx, m.x, m.y, 9, m.w, m.d, 2, COR.tampo);
  }

  function monitorFrente(ctx, x, y, desenharTela) {
    caixa(ctx, x + 0.28, y + 0.02, 11, 0.4, 0.24, 1, COR.monitor, false);
    caixa(ctx, x + 0.43, y + 0.06, 12, 0.1, 0.06, 4, COR.monitor, false);
    caixa(ctx, x, y, 15, 0.96, 0.09, 11, COR.monitor);
    if (desenharTela) desenharTela(y + 0.09, x + 0.07, x + 0.89, 16.5, 25);
  }

  function teclado(ctx, x, y) {
    caixa(ctx, x, y, 11, 0.76, 0.26, 1, COR.teclado, false);
    for (let r = 0; r < 2; r++) for (let i = 0; i < 6; i++) {
      const [px, py] = iso(x + 0.09 + i * 0.11, y + 0.08 + r * 0.1, 12);
      pixel(ctx, px, py, "#5f656e");
    }
    caixa(ctx, x + 0.86, y + 0.06, 11, 0.1, 0.14, 1, COR.teclado, false); // mouse
  }

  function pilhaPapel(ctx, x, y, n) {
    for (let i = 0; i < n; i++) caixa(ctx, x + (i % 2) * 0.03, y - i * 0.01, 11 + i, 0.42, 0.32, 1, COR.papel, false);
    const z = 11 + n;
    for (let i = 0; i < 3; i++) linha(ctx, iso(x + 0.06, y + 0.08 + i * 0.07, z), iso(x + 0.3, y + 0.08 + i * 0.07, z), "#a9a395");
  }

  function pastas(ctx, x, y, cores) {
    cores.forEach((cor, i) => {
      caixa(ctx, x + i * 0.11, y, 11, 0.09, 0.34, 10, tons(cor), false);
      faceY(ctx, y + 0.34, x + i * 0.11 + 0.01, x + i * 0.11 + 0.08, 15, 18, "#f2ede2");
    });
  }

  function caneca(ctx, x, y, cor) {
    caixa(ctx, x, y, 11, 0.13, 0.13, 3, tons(cor), false);
  }

  function arquivo(ctx, x, y, h = 30) {
    caixa(ctx, x, y, 0, 0.85, 0.7, h, COR.cinzaArquivo);
    const n = Math.round(h / 10);
    for (let i = 1; i < n; i++) faceY(ctx, y + 0.7, x + 0.03, x + 0.82, i * 10, i * 10 + 1, escurecer(COR.cinzaArquivo.esq, 0.25));
    for (let i = 0; i < n; i++) {
      faceY(ctx, y + 0.7, x + 0.32, x + 0.53, i * 10 + 6, i * 10 + 7, "#d4d8dd");
      faceY(ctx, y + 0.7, x + 0.12, x + 0.3, i * 10 + 3, i * 10 + 5, "#f2ede2");
    }
  }

  function estante(ctx, x, y, w) {
    caixa(ctx, x, y, 0, w, 0.5, 42, COR.madeiraEstante);
    const fy = y + 0.5;
    faceY(ctx, fy, x + 0.05, x + w - 0.05, 2, 40, "#3b2a1d");
    const cores = ["#2f5a85", "#b0473a", "#3f7a52", "#2b2f36", "#c99a3c", "#6b5b8f"];
    [3, 14].forEach((z, f) => {
      for (let k = 0; k < 8; k++) {
        const bx = x + 0.08 + k * ((w - 0.16) / 8);
        const cor = cores[(k + f * 3) % cores.length];
        faceY(ctx, fy, bx, bx + (w - 0.16) / 8 - 0.03, z, z + 9, cor);
        faceY(ctx, fy, bx + 0.03, bx + (w - 0.16) / 8 - 0.06, z + 5, z + 7, "#f2ede2");
      }
    });
    // caixas de arquivo morto
    for (let k = 0; k < 3; k++) {
      const bx = x + 0.08 + k * ((w - 0.16) / 3);
      faceY(ctx, fy, bx, bx + (w - 0.16) / 3 - 0.05, 26, 36, COR.caixaArquivo.esq);
      faceY(ctx, fy, bx + 0.12, bx + 0.32, 30, 32, "#f2ede2");
    }
    [13, 25, 37].forEach((z) => faceY(ctx, fy, x + 0.05, x + w - 0.05, z - 1, z, "#7b5a40"));
  }

  function planta(ctx, x, y, tamanho) {
    const h = tamanho === "g" ? 9 : 6;
    caixa(ctx, x, y, 0, 0.5, 0.5, h, COR.vaso);
    faceZ(ctx, x + 0.06, y + 0.06, x + 0.44, y + 0.44, h, "#4a3424");
    const [cx, cy] = iso(x + 0.25, y + 0.25, h);
    if (tamanho === "g") {
      linha(ctx, [cx, cy], [cx, cy - 14], "#5a3e28");
      [[-5, -16, 5, 1], [5, -18, 5, 0], [0, -24, 6, 2], [-6, -24, 4, 3], [6, -26, 4, 1], [0, -31, 5, 0], [-3, -12, 4, 3], [4, -11, 4, 2]]
        .forEach(([dx, dy, r, k]) => bolha(ctx, cx + dx, cy + dy, r, COR.folhas[k]));
      [[-2, -26], [3, -20], [-6, -18], [1, -33]].forEach(([dx, dy]) => pixel(ctx, cx + dx, cy + dy, "#7cc08f"));
    } else {
      [[-3, -4, 3, 0], [3, -5, 3, 1], [0, -8, 3, 2]].forEach(([dx, dy, r, k]) => bolha(ctx, cx + dx, cy + dy, r, COR.folhas[k]));
    }
  }

  function divisoriaVidro(ctx, x, y, w, d) {
    caixa(ctx, x, y, 0, w, d, 6, tons("#4e5763"));
    ctx.save();
    ctx.globalAlpha = 0.28;
    caixa(ctx, x, y, 6, w, d, 12, { topo: "#d8eef7", esq: "#a9d3e6", dir: "#93c3d9" }, false);
    ctx.restore();
    caixa(ctx, x, y, 18, w, d, 1, tons("#4e5763"), false);
    const passo = 1.4;
    if (w > d) for (let a = x; a <= x + w; a += passo) caixa(ctx, Math.min(a, x + w - 0.08), y, 6, 0.08, d, 12, tons("#4e5763"), false);
    else for (let a = y; a <= y + d; a += passo) caixa(ctx, x, Math.min(a, y + d - 0.08), 6, w, 0.08, 12, tons("#4e5763"), false);
  }

  function cadeiraSimples(ctx, x, y, lado, cores = COR.cadeiraClara) {
    caixa(ctx, x + 0.2, y + 0.2, 0, 0.1, 0.1, 5, COR.metal, false);
    caixa(ctx, x, y, 5, 0.5, 0.5, 2, cores);
    const encosto = {
      n: [x, y, 0.5, 0.1], s: [x, y + 0.4, 0.5, 0.1], o: [x, y, 0.1, 0.5], l: [x + 0.4, y, 0.1, 0.5]
    }[lado];
    caixa(ctx, encosto[0], encosto[1], 7, encosto[2], encosto[3], 8, cores);
  }

  // Identidade visual de cada estação (itens antes e depois do monitor/teclado).
  // Documentos: bandeja de entrada, fileira de pastas, gaveteiro e detalhes em verde-petróleo.
  const ESTACOES = {
    documentos: {
      antes(c, m) {
        faceZ(c, m.x + 0.95, m.y + 0.52, m.x + 1.98, m.y + 1.06, 11, "#2a6f67");
        // gaveteiro ao lado da mesa
        caixa(c, m.x + m.w + 0.06, m.y + 0.3, 0, 0.42, 0.68, 17, COR.cinzaArquivo);
        [6, 12].forEach((z) => faceY(c, m.y + 0.98, m.x + m.w + 0.08, m.x + m.w + 0.46, z, z + 1, escurecer(COR.cinzaArquivo.esq, 0.25)));
        [2, 8, 14].forEach((z) => faceY(c, m.y + 0.98, m.x + m.w + 0.14, m.x + m.w + 0.28, z, z + 2, "#2f8f83"));
      },
      depois(c, m) {
        // bandeja de entrada em dois andares
        const bx = m.x + 1.5;
        const by = m.y + 0.1;
        caixa(c, bx, by, 11, 0.52, 0.4, 1, tons("#2f8f83"), false);
        caixa(c, bx + 0.04, by + 0.04, 12, 0.44, 0.32, 2, COR.papel, false);
        caixa(c, bx + 0.02, by + 0.02, 14, 0.04, 0.04, 4, tons("#2f8f83"), false);
        caixa(c, bx + 0.46, by + 0.34, 14, 0.04, 0.04, 4, tons("#2f8f83"), false);
        caixa(c, bx, by, 18, 0.52, 0.4, 1, tons("#2f8f83"), false);
        caixa(c, bx + 0.06, by + 0.04, 19, 0.42, 0.32, 1, COR.papel, false);
        // fileira de pastas
        pastas(c, m.x + 1.95, m.y + 0.62, ["#2f8f83", "#c99a3c", "#2f8f83"]);
        caneca(c, m.x + 0.12, m.y + 0.8, "#2f8f83");
        pilhaPapel(c, m.x + 0.12, m.y + 0.28, 2);
      }
    }
  };

  // Importação VGROW (especialista da Contabilidade): pastas por processo, calculadora e contêiner em miniatura.
  ESTACOES.importacao = {
    antes(c, m) {
      faceZ(c, m.x + 0.95, m.y + 0.52, m.x + 1.98, m.y + 1.06, 11, "#2f4f7a");
    },
    depois(c, m) {
      pastas(c, m.x + 1.6, m.y + 0.12, ["#c99a3c", "#2f4f7a", "#c99a3c", "#2f4f7a"]);
      // calculadora
      caixa(c, m.x + 0.14, m.y + 0.72, 11, 0.32, 0.36, 1, tons("#3a3f47"), false);
      faceZ(c, m.x + 0.18, m.y + 0.75, m.x + 0.42, m.y + 0.84, 12, "#9fd3a8");
      // contêiner em miniatura (processos de importação)
      caixa(c, m.x + 2.0, m.y + 0.72, 11, 0.24, 0.36, 3, tons("#b0473a"), false);
      pilhaPapel(c, m.x + 0.12, m.y + 0.2, 3);
    }
  };

  function placaVaga(ctx, x, y) {
    caixa(ctx, x, y, 11, 0.42, 0.06, 6, tons("#e8e2d6"), false);
    const [px, py] = iso(x + 0.21, y + 0.06, 14);
    ctx.fillStyle = "#8a93a0";
    ctx.fillRect(Math.round(px) - 1, Math.round(py) - 2, 3, 1);
    ctx.fillRect(Math.round(px), Math.round(py) - 3, 1, 3);
  }

  function pastaNaMesa(c, x, y, z, bloqueada) {
    caixa(c, x, y, z, 0.6, 0.42, 2, tons("#e2b04a"));
    caixa(c, x + 0.05, y + 0.05, z + 2, 0.5, 0.32, 1, COR.papel, false);
    caixa(c, x + 0.04, y + 0.3, z + 2, 0.22, 0.12, 1, tons(bloqueada ? "#e25d5d" : "#c99a3c"), false);
    if (bloqueada) {
      const [px, py] = iso(x + 0.3, y + 0.2, z + 12);
      c.fillStyle = "#1b1d22";
      c.fillRect(Math.round(px) - 3, Math.round(py) - 5, 7, 10);
      c.fillStyle = "#e25d5d";
      c.fillRect(Math.round(px) - 2, Math.round(py) - 4, 5, 8);
      c.fillStyle = "#ffffff";
      c.fillRect(Math.round(px), Math.round(py) - 3, 1, 4);
      c.fillRect(Math.round(px), Math.round(py) + 2, 1, 1);
    }
  }

  function telaApagada(ctx) {
    return (fy, x0, x1, z0, z1) => faceY(ctx, fy, x0, x1, z0, z1, "#15171b");
  }

  // Lista de objetos fixos com a área de sombra no piso.
  function objetosFixos() {
    const lista = [];
    const add = (chave, sombra, fn) => lista.push({ chave, sombra, fn });

    // ---- sala do coordenador
    add(4.4, [3.9, 0.15, 1.7, 0.5], (c) => estante(c, 3.9, 0.15, 1.7));
    add(1.2, [5.1, 0.35, 0.5, 0.5], (c) => planta(c, 5.1, 0.35, "g"));
    add(4.1, [0.15, 3.3, 0.85, 0.7], (c) => arquivo(c, 0.15, 3.3, 30));
    add(5.0, [0.15, 4.15, 0.85, 0.7], (c) => arquivo(c, 0.15, 4.15, 30));
    add(6.6, [1.8, 4.3, 0.5, 0.5], (c) => cadeiraSimples(c, 1.8, 4.3, "s"));
    add(7.8, [3.0, 4.3, 0.5, 0.5], (c) => cadeiraSimples(c, 3.0, 4.3, "s"));
    add(9.05, null, (c) => divisoriaVidro(c, 6.0, 0, 0.1, 6.0));
    add(8.15, null, (c) => divisoriaVidro(c, 0, 6.0, 4.3, 0.1));

    // ---- divisórias de tecido entre as estações
    [10.5, 13.7, 16.9].forEach((x) => add(x + 1.1, [x, 0.25, 0.1, 1.5], (c) => {
      caixa(c, x, 0.25, 0, 0.1, 1.5, 22, COR.divisoria);
      caixa(c, x, 0.25, 22, 0.1, 1.5, 1, tons("#3a475a"), false);
    }));

    // ---- estações reservadas (vagas)
    VAGAS.forEach((v) => {
      const m = v.mesa;
      add(m.x + m.w / 2 + m.y + m.d / 2, [m.x, m.y, m.w, m.d], (c) => {
        mesaTrabalho(c, m);
        monitorFrente(c, m.x + 0.3, m.y + 0.18, telaApagada(c));
        placaVaga(c, m.x + 1.5, m.y + 0.35);
      });
      add(v.pessoa.x + v.pessoa.y, null, (c) => {
        const [sx, sy] = origemSprite(...iso(v.pessoa.x, v.pessoa.y));
        desenharSprite(c, SPRITE_COSTAS, PALETA_BASE, sx, sy, { de: LINHA_CADEIRA });
      });
    });

    // ---- impressora/copiadora e arquivo do corredor
    add(19.3, [13.4, 7.0, 1.05, 0.8], (c) => {
      caixa(c, 13.4, 7.0, 0, 1.05, 0.8, 14, tons("#d9dde2"));
      caixa(c, 13.45, 7.05, 14, 0.95, 0.7, 4, tons("#eceff2"));
      caixa(c, 13.55, 7.6, 14, 0.4, 0.15, 3, tons("#4a515b"), false);
      faceY(c, 7.75, 13.6, 13.75, 15, 16, "#7fe0a8");
      caixa(c, 13.55, 7.1, 18, 0.6, 0.45, 1, COR.papel, false);
      faceY(c, 7.8, 13.5, 14.3, 4, 5, "#9ba2ab");
      faceY(c, 7.8, 13.5, 14.3, 9, 10, "#9ba2ab");
    });
    add(18.1, [13.4, 4.2, 0.5, 0.5], (c) => planta(c, 13.4, 4.2, "g"));
    add(10.9, [6.9, 3.6, 0.85, 0.7], (c) => arquivo(c, 6.9, 3.6, 20));

    // ---- área de reunião
    add(25.0, [14.7, 6.6, 3.4, 1.6], (c) => {
      caixa(c, 15.4, 7.2, 0, 0.3, 0.3, 10, COR.metal, false);
      caixa(c, 17.1, 7.2, 0, 0.3, 0.3, 10, COR.metal, false);
      caixa(c, 14.7, 6.6, 10, 3.4, 1.6, 2, COR.nogueira);
      // notebook, papéis e garrafas
      caixa(c, 15.1, 6.9, 12, 0.55, 0.4, 1, tons("#9da3ab"), false);
      faceY(c, 6.9, 15.1, 15.65, 13, 19, "#2c3038");
      faceY(c, 6.9, 15.15, 15.6, 14, 18, "#23405c");
      pilhaPapel(c, 16.3, 7.3, 2);
      caixa(c, 17.4, 6.9, 12, 0.1, 0.1, 5, tons("#8cc4e0"), false);
      caixa(c, 17.6, 7.6, 12, 0.1, 0.1, 5, tons("#8cc4e0"), false);
    });
    [[15.0, 5.95, "n"], [16.4, 5.95, "n"], [14.05, 7.15, "o"]].forEach(([x, y, l]) => add(x + y, [x, y, 0.5, 0.5], (c) => cadeiraSimples(c, x, y, l)));
    [[15.0, 8.35, "s"], [16.4, 8.35, "s"], [18.25, 7.15, "l"]].forEach(([x, y, l]) => add(x + y + 1.4, [x, y, 0.5, 0.5], (c) => cadeiraSimples(c, x, y, l)));
    add(25.6, [19.15, 5.9, 0.5, 0.6], (c) => {
      // cavalete com gráfico
      caixa(c, 19.2, 6.4, 0, 0.06, 0.06, 26, COR.metal, false);
      caixa(c, 19.55, 6.4, 0, 0.06, 0.06, 26, COR.metal, false);
      faceY(c, 6.5, 19.15, 19.7, 12, 30, "#f6f3ec");
      [[0.05, 4], [0.18, 7], [0.31, 5], [0.44, 10]].forEach(([dx, h]) => faceY(c, 6.5, 19.2 + dx, 19.28 + dx, 14, 14 + h, "#2f5a85"));
    });
    add(28.6, [19.2, 9.2, 0.5, 0.5], (c) => planta(c, 19.2, 9.2, "g"));
    add(22.4, [19.25, 2.6, 0.5, 0.5], (c) => planta(c, 19.25, 2.6, "p"));

    // ---- área de descanso
    add(10.2, [0.3, 8.2, 1.1, 3.0], (c) => {
      caixa(c, 0.3, 8.2, 0, 1.1, 3.0, 6, COR.sofa);
      caixa(c, 0.3, 8.2, 6, 0.3, 3.0, 12, COR.sofa);
      [0, 1, 2].forEach((i) => caixa(c, 0.6, 8.32 + i * 0.95, 6, 0.75, 0.88, 3, COR.almofada));
      caixa(c, 0.3, 8.2, 6, 1.1, 0.24, 6, COR.sofa);
      caixa(c, 0.3, 10.96, 6, 1.1, 0.24, 6, COR.sofa);
      caixa(c, 0.62, 8.5, 9, 0.18, 0.45, 5, tons("#c99a3c"), false);
    });
    add(12.2, [2.2, 9.1, 1.1, 1.4], (c) => {
      caixa(c, 2.2, 9.1, 0, 1.1, 1.4, 6, COR.nogueira);
      caixa(c, 2.35, 9.3, 6, 0.4, 0.5, 1, tons("#b0473a"), false);
      caixa(c, 2.4, 9.35, 7, 0.4, 0.5, 1, tons("#2f5a85"), false);
      caixa(c, 2.95, 9.9, 6, 0.13, 0.13, 3, tons("#f2ede2"), false);
    });
    add(13.9, [4.1, 9.2, 0.9, 0.9], (c) => {
      caixa(c, 4.1, 9.2, 0, 0.9, 0.9, 6, COR.almofada);
      caixa(c, 4.75, 9.2, 6, 0.25, 0.9, 8, COR.sofa);
      caixa(c, 4.1, 9.2, 6, 0.9, 0.18, 5, COR.sofa);
      caixa(c, 4.1, 9.92, 6, 0.9, 0.18, 5, COR.sofa);
    });
    add(13.2, [0.2, 11.6, 1.0, 1.25], (c) => {
      caixa(c, 0.2, 11.6, 0, 1.0, 1.25, 15, COR.bancada);
      faceX(c, 1.2, 11.7, 12.2, 2, 13, escurecer(COR.bancada.dir, 0.06));
      faceX(c, 1.2, 12.25, 12.75, 2, 13, escurecer(COR.bancada.dir, 0.06));
      caixa(c, 0.32, 11.75, 15, 0.55, 0.5, 11, COR.maquina);
      faceY(c, 12.25, 0.45, 0.75, 20, 23, "#1b1d22");
      pixel(c, ...iso(0.8, 12.25, 24), "#e25d5d");
      [0, 1, 2].forEach((i) => caixa(c, 0.4 + i * 0.18, 12.45, 15, 0.12, 0.12, 3, tons("#f2ede2"), false));
    });
    add(12.4, [4.6, 7.4, 0.55, 0.55], (c) => {
      caixa(c, 4.6, 7.4, 0, 0.55, 0.55, 16, COR.branco);
      faceY(c, 7.95, 4.68, 4.85, 9, 11, "#5aa7e6");
      garrafaAgua(c, 4.68, 7.48);
    });
    add(16.9, [5.0, 11.9, 0.5, 0.5], (c) => planta(c, 5.0, 11.9, "g"));
    add(13.1, [0.5, 6.7, 0.3, 0.3], (c) => {
      // luminária de chão
      caixa(c, 0.5, 6.7, 0, 0.3, 0.3, 1, COR.metal, false);
      caixa(c, 0.62, 6.82, 1, 0.06, 0.06, 30, COR.metal, false);
      caixa(c, 0.45, 6.65, 30, 0.4, 0.4, 6, tons("#efe3c4"), false);
    });
    add(31.4, [19.25, 11.9, 0.5, 0.5], (c) => planta(c, 19.25, 11.9, "g"));
    // meia-parede da copa (separa o descanso das estações; passagem entre o bebedouro e a parede)
    add(16.5, [5.95, 8.3, 0.18, 4.4], (c) => {
      caixa(c, 5.95, 8.3, 0, 0.18, 4.4, 14, tons("#cfc6b6"));
      caixa(c, 5.92, 8.3, 14, 0.24, 4.4, 2, tons("#8e6b4f"), false);
      [8.6, 9.7, 10.8, 11.9].forEach((y) => [[-3, 0, 2], [3, 1, 2], [0, 2, 3]].forEach(([dx, k, r]) => {
        const [px, py] = iso(6.04, y + 0.25, 16);
        bolha(c, px + dx, py - 2, r, COR.folhas[k]);
      }));
    });
    return lista;
  }

  // Áreas ocupadas no piso para a grade de caminhos: móveis com sombra, mesas e divisórias de vidro.
  function ocupacoes(fixos) {
    return fixos.map((o) => o.sombra).filter(Boolean)
      .concat(Object.values(POSTOS).concat(VAGAS).map((p) => [p.mesa.x, p.mesa.y, p.mesa.w, p.mesa.d]))
      .concat([[6.0, 0, 0.1, 6.0], [0, 6.0, 4.3, 0.1]]);
  }

  function garrafaAgua(c, x, y) {
    c.save();
    c.globalAlpha = 0.85;
    caixa(c, x, y, 16, 0.38, 0.38, 10, COR.agua, false);
    c.restore();
    faceY(c, y + 0.38, x + 0.06, x + 0.12, 18, 24, "#d6ecf6");
  }

  // Pontos de luz (desenhados por cima, mais fortes à noite).
  const LUZES = [
    { x: 0.65, y: 6.85, z: 32, raio: 34 },
    { x: 4.4, y: 2.6, z: 16, raio: 18 }
  ];

  // ================================================================ telas e balões por estado
  function desenharTela(ctx, status, quadro) {
    return (fy, x0, x1, z0, z1) => {
      const fundo = {
        LIVRE: "#23405c",
        TRABALHANDO: "#e9eef2",
        AGUARDANDO_SUPERVISOR: quadro % 8 < 4 ? "#6a4d1e" : "#56401a",
        PENDENCIA: "#5c5220",
        CONCLUIDO: "#1f4d35",
        ERRO: quadro % 2 ? "#8a2222" : "#b33030",
        OFFLINE: "#121417",
        NAO_IMPLEMENTADO: "#121417"
      }[status] || "#121417";
      faceY(ctx, fy, x0, x1, z0, z1, fundo);
      const faixa = (z, a, b, cor) => faceY(ctx, fy, x0 + a * (x1 - x0), x0 + b * (x1 - x0), z, z + 1, cor);
      if (status === "TRABALHANDO") {
        // planilha rolando
        faixa(z1 - 2, 0, 1, "#2f6fa8");
        for (let i = 0; i < 3; i++) {
          const z = z0 + 1 + ((i * 2 + quadro) % 6);
          faixa(z, 0.08, 0.3, "#9aa3ad");
          faixa(z, 0.38, 0.38 + ((i * 37 + quadro * 13) % 40) / 100, "#5aa7e6");
        }
      } else if (status === "LIVRE") {
        faixa(z1 - 3, 0.1, 0.9, "#35577a");
        if (quadro % 6 < 3) faixa(z0 + 2, 0.1, 0.2, "#9ccdf0");
      } else if (status === "PENDENCIA") {
        faixa(z0 + 3, 0.15, 0.85, "#f2d45c");
      } else if (status === "CONCLUIDO") {
        faixa(z0 + 3, 0.2, 0.7, "#7fe0a8");
        faixa(z0 + 5, 0.2, 0.5, "#7fe0a8");
      } else if (status === "AGUARDANDO_SUPERVISOR") {
        faixa(z0 + 3, 0.4, 0.6, "#f6d9a6");
      }
    };
  }

  function desenharBalao(ctx, status, ax, ay, quadro, reduzido) {
    const estilo = BALAO[status];
    const glifo = GLIFOS[status];
    if (!estilo || !glifo) return;
    let dy = 0;
    let dx = 0;
    if (!reduzido) {
      if (status === "PENDENCIA") dy = [0, -1, -2, -1][quadro % 4];
      if (status === "ERRO") dx = quadro % 2 ? 1 : -1;
      if (status === "OFFLINE") dy = -(quadro % 4);
    }
    const x = Math.round(ax - 6 + dx);
    const y = Math.round(ay - TOPO_CABECA - 18 + dy);
    ctx.fillStyle = "rgba(0, 0, 0, 0.25)";
    ctx.fillRect(x + 2, y + 2, 11, 11);
    ctx.fillStyle = "#1b1d22";
    ctx.fillRect(x + 1, y, 11, 13);
    ctx.fillRect(x, y + 1, 13, 11);
    ctx.fillStyle = estilo.fundo;
    ctx.fillRect(x + 1, y + 1, 11, 11);
    ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
    ctx.fillRect(x + 1, y + 1, 11, 1);
    ctx.fillStyle = "#1b1d22";
    ctx.fillRect(x + 5, y + 13, 3, 1);
    ctx.fillRect(x + 6, y + 14, 1, 1);
    if (status === "AGUARDANDO_SUPERVISOR" && !reduzido && quadro % 6 < 3) {
      ctx.strokeStyle = "#f0b74a";
      ctx.lineWidth = 1;
      ctx.strokeRect(x - 0.5, y - 0.5, 14, 14);
    }
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < 7; c++) if (glifo[r][c] === "x") pixel(ctx, x + 3 + c, y + 3 + r, estilo.glifo);
    }
    if (status === "TRABALHANDO") {
      const n = reduzido ? 3 : quadro % 4;
      for (let i = 0; i < n; i++) pixel(ctx, x + 15 + i * 2, y + 11, "#9ccdf0");
    }
  }

  function brilhos(ctx, ax, ay, quadro) {
    [[-12, -32], [12, -27], [-10, -10], [13, -12]].forEach(([dx, dy], i) => {
      if ((quadro + i) % 4 !== 0) return;
      ctx.fillStyle = "#fff4c2";
      ctx.fillRect(ax + dx, ay + dy - 1, 1, 3);
      ctx.fillRect(ax + dx - 1, ay + dy, 3, 1);
    });
  }

  function seta(ctx, ax, ay, t, reduzido) {
    const dy = reduzido ? 0 : Math.round(Math.sin(t / 220) * 1.5);
    const x = Math.round(ax);
    const y = Math.round(ay - TOPO_CABECA - 25 + dy);
    ctx.fillStyle = "#1b1d22";
    ctx.fillRect(x - 4, y - 1, 9, 1);
    for (let i = 0; i < 4; i++) ctx.fillRect(x - 4 + i, y + i, 9 - 2 * i, 1);
    ctx.fillStyle = COR.selecao;
    for (let i = 0; i < 3; i++) ctx.fillRect(x - 3 + i, y + i, 7 - 2 * i, 1);
  }

  // Halo pulsante no piso para estados que pedem atenção do Supervisor.
  const ATENCAO = {
    AGUARDANDO_SUPERVISOR: "240, 183, 74",
    PENDENCIA: "232, 207, 82",
    ERRO: "226, 93, 93"
  };

  function halo(ctx, status, x, y, t, reduzido) {
    const cor = ATENCAO[status];
    if (!cor) return;
    const pulso = reduzido ? 0.5 : 0.5 + 0.5 * Math.sin(t / (status === "ERRO" ? 140 : 260));
    const r = 0.95 + 0.12 * pulso;
    ctx.fillStyle = `rgba(${cor}, ${0.18 + 0.2 * pulso})`;
    ctx.beginPath();
    [iso(x - r, y), iso(x, y - r), iso(x + r, y), iso(x, y + r)].forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.closePath();
    ctx.fill();
  }

  // ================================================================ personagens
  // corpo: { pose: "mesa" | "pe" | "sentado", x, y, z, vista, passo, carregando } (personagens que caminham);
  // sem corpo, o personagem é desenhado sentado no próprio posto.
  function desenharAgente(ctx, agente, estado, quadro, reduzido, corpo) {
    const posto = POSTOS[agente.id];
    const status = estado.status;
    const pose = corpo ? corpo.pose : "mesa";
    const paleta = paletaDe(agente.id, status);

    if (status === "NAO_IMPLEMENTADO") {
      const [ax, ay] = iso(posto.pessoa.x, posto.pessoa.y);
      const [sx, sy] = origemSprite(ax, ay);
      desenharSprite(ctx, SPRITE_COSTAS, PALETA_BASE, sx, sy, { de: LINHA_CADEIRA });
      ctx.save();
      ctx.globalAlpha = 0.38;
      desenharSprite(ctx, SPRITE_COSTAS, paleta, sx, sy, { ate: LINHA_CADEIRA, corUnica: "#a99fd0" });
      ctx.restore();
      return;
    }

    if (pose !== "mesa") {
      // em pé (andando ou parado) ou sentado na copa
      const [ax, ay] = iso(corpo.x, corpo.y, pose === "sentado" ? corpo.z : 0);
      const sx = Math.round(ax - 7 * ESC_PESSOA);
      const sy = pose === "sentado" ? Math.round(ay + 3 - SPRITE_SENTADO.length * ESC_PESSOA) : origemSprite(ax, ay)[1];
      ctx.save();
      if (status === "OFFLINE") ctx.globalAlpha = 0.85;
      let sprite = pose === "sentado" ? SPRITE_SENTADO : corpo.vista === "frente" ? SPRITE_FRENTE : SPRITE_PE_COSTAS;
      if (pose === "pe" && corpo.passo) sprite = sprite.slice(0, 20).concat(PERNAS_PASSO);
      desenharSprite(ctx, sprite, paleta, sx, sy);
      const detalhes = DETALHES[agente.id] || [];
      // os detalhes de frente (têmporas) e de costas (rabo de cavalo, coque) só aparecem do lado certo
      detalhes.filter(([, r]) => pose === "pe" && corpo.vista !== "frente" ? true : r < 8).forEach(([c, r, k]) => celula(ctx, sx, sy, c, r, paleta[k]));
      if (corpo.carregando) {
        // envelope com os documentos da tarefa (acompanha a caminhada, não substitui)
        const ex = sx + Math.round(10 * ESC_PESSOA);
        const ey = sy + Math.round(13 * ESC_PESSOA);
        ctx.fillStyle = "#1b1d22";
        ctx.fillRect(ex - 1, ey - 1, 8, 7);
        ctx.fillStyle = "#f2e2b8";
        ctx.fillRect(ex, ey, 6, 5);
        ctx.fillStyle = "#c99a3c";
        ctx.fillRect(ex, ey, 6, 1);
        ctx.fillRect(ex + 2, ey + 1, 2, 1);
      }
      ctx.restore();
      return;
    }

    const [ax, ay] = iso(posto.pessoa.x, posto.pessoa.y);
    const tremor = status === "ERRO" && !reduzido ? (quadro % 2 ? 1 : -1) : 0;
    const [ox, sy] = origemSprite(ax, ay);
    const sx = ox + tremor;
    const frente = posto.vista === "frente";
    ctx.save();
    if (status === "OFFLINE") ctx.globalAlpha = 0.85;
    if (frente) {
      // poltrona de encosto alto atrás do coordenador (em células do sprite)
      const e = ESC_PESSOA;
      ctx.fillStyle = "#1b1d22";
      ctx.fillRect(Math.round(sx - 2 * e), Math.round(sy + e), Math.round(18 * e), Math.round(17 * e));
      ctx.fillStyle = "#3b2a22";
      ctx.fillRect(Math.round(sx - e), Math.round(sy + 2 * e), Math.round(16 * e), Math.round(15 * e));
      ctx.fillStyle = "#4e382c";
      ctx.fillRect(Math.round(sx), Math.round(sy + 3 * e), Math.round(14 * e), Math.round(3 * e));
    }
    const sprite = frente ? SPRITE_FRENTE : SPRITE_COSTAS;
    const cabecaBaixa = status === "OFFLINE" ? { deslocarAte: 9, deslocamento: 1 } : {};
    desenharSprite(ctx, sprite, paleta, sx, sy, cabecaBaixa);
    (DETALHES[agente.id] || []).forEach(([c, r, k]) => celula(ctx, sx, sy, c, r + (cabecaBaixa.deslocamento && r < 9 ? 1 : 0), paleta[k]));

    // braços conforme o estado
    const p = (c, r, cor) => celula(ctx, sx, sy, c, r, cor);
    const bracoBaixo = (col, desl) => { p(col, 10 + desl, paleta.c); p(col, 11 + desl, paleta.C); p(col, 12 + desl, paleta.s); };
    const bracoAlto = (col) => { [9, 8, 7, 6, 5].forEach((r) => p(col, r, paleta.c)); p(col, 4, paleta.s); p(col, 3, paleta.s); };
    if (!frente) {
      if (status === "TRABALHANDO") {
        const a = reduzido ? 0 : quadro % 2;
        bracoBaixo(0, a); bracoBaixo(13, 1 - a);
      } else if (status === "AGUARDANDO_SUPERVISOR") {
        bracoBaixo(0, 0); bracoAlto(13);
      } else if (status === "CONCLUIDO" && !reduzido && quadro % 8 < 3) {
        bracoAlto(0); bracoAlto(13);
      } else if (status === "PENDENCIA") {
        bracoBaixo(0, 0); [9, 8, 7, 6].forEach((r) => p(12, r, paleta.c)); p(11, 5, paleta.s);
      } else if (status === "LIVRE") {
        bracoBaixo(0, 0); bracoBaixo(13, 1); p(13, 13, "#f2ede2"); p(14, 13, "#f2ede2"); p(13, 14, "#d8d3c8");
      } else {
        bracoBaixo(0, 1); bracoBaixo(13, 1);
      }
    } else {
      if (status === "TRABALHANDO" && !reduzido) {
        p(2, 14 + (quadro % 2), paleta.s); p(11, 15 - (quadro % 2), paleta.s);
      } else if (status === "AGUARDANDO_SUPERVISOR") {
        [13, 12, 11, 10, 9, 8, 7].forEach((r) => p(13, r, paleta.c)); p(13, 6, paleta.s); p(13, 5, paleta.s); p(14, 6, PALETA_BASE.o);
      } else if (status === "CONCLUIDO" && !reduzido && quadro % 8 < 3) {
        [13, 12, 11, 10, 9, 8].forEach((r) => { p(0, r, paleta.c); p(13, r, paleta.c); });
        p(0, 7, paleta.s); p(13, 7, paleta.s);
      }
    }
    ctx.restore();
  }

  // ================================================================ caminhada dos personagens funcionais
  // A caminhada só ACOMPANHA o estado real: o destino vem de estado.local ("mesa" | "copa") e as idas ao Coordenador
  // vêm de estado.eventos (buscar/entregar, com horário). Nada aqui dispara, aprova ou repete operações.
  // - eventos com horário anterior ao carregamento da página nunca são animados (recarregar não repete entregas);
  // - cada evento é considerado uma única vez (identificador);
  // - etapas rápidas mantêm a reprodução visual buscar → própria mesa → entregar; a execução real não é atrasada;
  // - movimento reduzido: o personagem é colocado direto no lugar atual, sem caminhada.
  const VELOCIDADE = 2.6;   // ladrilhos por segundo
  const PAUSA_COORDENADOR = 900;

  function criarCaminhada(app, grade, reduzido, carregadoEm) {
    const caminhantes = app.agentes.filter((a) => a.implementado && POSTOS[a.id] && POSTOS[a.id].caminha).map((a) => a.id);
    const corpos = {};
    const vistos = new Set();
    const entregas = new Set();
    const desejado = (id) => (app.estadoDe(id).local === "copa" ? "copa" : "mesa");

    function lugarCopa(id) {
      const c = corpos[id];
      if (c && c.assento !== null && c.assento !== undefined) return c.assento;
      const ocupados = new Set(caminhantes.filter((o) => o !== id && corpos[o]).map((o) => corpos[o].assento).filter((k) => k !== null && k !== undefined));
      // preferência: pontas do sofá, poltrona, meio do sofá; depois em pé
      const k = [0, 2, 3, 1].find((n) => !ocupados.has(n)) ?? (() => { let n = COPA.assentos.length; while (ocupados.has(n)) n++; return n; })();
      if (c) c.assento = k;
      return k;
    }

    function destinoFinal(id) {
      if (desejado(id) === "mesa") return { tipo: "mesa", ponto: POSTOS[id].pessoa };
      const k = lugarCopa(id);
      return k < COPA.assentos.length ? { tipo: "assento", ponto: COPA.assentos[k], assento: COPA.assentos[k] }
        : { tipo: "copa-em-pe", ponto: COPA.emPe[(k - COPA.assentos.length) % COPA.emPe.length] };
    }

    function colocar(id) {
      corpos[id] = corpos[id] || { assento: null };
      const c = corpos[id];
      if (desejado(id) !== "copa") c.assento = null;
      const d = destinoFinal(id);
      Object.assign(c, { pos: { x: d.ponto.x, y: d.ponto.y }, caminho: [], alvo: d, visita: null, visitaFeita: null,
                         carregando: false, pausaAte: 0, direcao: 1, distancia: 0, fila: [] });
    }

    function replanejar(id) {
      const c = corpos[id];
      if (desejado(id) !== "copa") c.assento = null;
      if (!c.visita && c.fila.length) {
        if(c.fila[0].espera && !entregas.has(c.fila[0].espera))return;
        c.visita = c.fila.shift();
      }
      const alvo = c.visita ? (c.visita.tipo === 'trabalhar'
        ? { tipo: 'mesa', ponto: POSTOS[id].pessoa, destino: id }
        : { tipo: "visita", ponto: ENTREGA[c.visita.destino] || VISITA_COORDENADOR, destino: c.visita.destino }) : destinoFinal(id);
      alvo.visita = c.visita;
      if (c.alvo && c.alvo.tipo === alvo.tipo && c.alvo.ponto === alvo.ponto && c.alvo.visita === alvo.visita) return;
      c.alvo = alvo;
      c.carregando = (c.visita && c.visita.tipo === "entregar") || (c.carregando && alvo.tipo === "mesa");
      const caminho = planejarCaminho(grade, c.pos, alvo.ponto);
      c.caminho = caminho ? caminho.slice(1) : [{ x: alvo.ponto.x, y: alvo.ponto.y }];
    }

    function sincronizar() {
      const retrato=caminhantes.flatMap(id=>app.estadoDe(id).eventos || []);
      if(retrato.some(e=>!vistos.has(e.id)) && retrato.every(e=>Date.parse(e.em)<carregadoEm)
          && caminhantes.every(id=>!corpos[id]?.visita && !corpos[id]?.fila?.length)) {
        retrato.forEach(e=>{vistos.add(e.id);if(e.tipo==='entregar')entregas.add(e.id);});
        // Também posiciona os não acionados: uma recarga não deve animar a troca de assento na copa.
        caminhantes.forEach(colocar);
        return;
      }
      caminhantes.forEach((id) => {
        const eventos = app.estadoDe(id).eventos || [];
        const novos = eventos.filter((e) => e && e.id && !vistos.has(e.id));
        novos.forEach((e) => vistos.add(e.id));
        if (!corpos[id] || reduzido) {
          eventos.filter(e=>e.tipo==='entregar').forEach(e=>entregas.add(e.id));
          colocar(id);
          return;
        }
        const c = corpos[id];
        const recentes = novos.filter((e) => Date.parse(e.em) >= carregadoEm);
        novos.filter(e=>Date.parse(e.em)<carregadoEm && e.tipo==='entregar').forEach(e=>entregas.add(e.id));
        // O primeiro retrato da API substitui o cenário provisório sem encenar o passado.
        if(novos.length && !recentes.length && !c.visita && !c.fila.length) {
          colocar(id);
          return;
        }
        // Não descarta buscar/trabalhar quando a etapa termina antes do próximo polling.
        recentes.forEach(e => {
          const partes=e.id.split(':');let espera=null;
          if(e.tipo==='trabalhar' && id==='financeiro' && partes[2]==='1')espera=partes[0]+':doc:entregar:financeiro';
          if(e.tipo==='trabalhar' && id==='fiscal' && partes[2]==='1')espera=partes[0]+':doc:entregar:fiscal';
          if(e.tipo==='trabalhar' && id==='dp' && partes[2]==='1')espera=partes[0]+':doc:entregar:dp';
          // Conciliação só trabalha depois que a Contabilidade entrega o conjunto das propostas (mesma tentativa)
          if(e.tipo==='trabalhar' && id==='conciliacao') {
            const entrega=(app.estadoDe('bancos').eventos || []).find(v=>v.id===`${partes[0]}:ban:C${partes[2]}:entregar:conciliacao`);
            espera=entrega ? entrega.id : null;
          }
          if(e.tipo==='trabalhar' && id==='bancos') {
            // As tentativas das áreas têm numeração independente (F = Fiscal, D = DP, sem prefixo = Financeiro).
            const marca=String(partes[2]||'').charAt(0);
            const [agOrigem,pref]=marca==='F'?['fiscal',':fis:']:marca==='D'?['dp',':dpa:']:['financeiro',':fin:'];
            const origem=(app.estadoDe(agOrigem).eventos || [])
              .filter(v=>v.id.startsWith(partes[0]+pref) && v.tipo==='entregar' && v.destino==='bancos' && Date.parse(v.em)<=Date.parse(e.em))
              .sort((a,b)=>Date.parse(b.em)-Date.parse(a.em))[0];
            espera=origem ? origem.id : null;
          }
          c.fila.push({id:e.id,tipo:e.tipo,destino:e.destino || 'coordenador',espera});
        });
        if (!c.pausaAte) replanejar(id);
      });
    }

    // Avança a caminhada; devolve true enquanto alguém estiver em movimento ou em pausa.
    function avancar(dt, t) {
      let ativo = false;
      caminhantes.forEach((id) => {
        const c = corpos[id];
        if (!c) return;
        if (c.pausaAte) {
          ativo = true;
          if (t < c.pausaAte) return;
          c.pausaAte = 0;
          if(c.visitaFeita && c.visitaFeita.tipo==='entregar')entregas.add(c.visitaFeita.id);
          c.carregando = !!c.visitaFeita && c.visitaFeita.tipo === "buscar";
          c.visita = null;
          c.visitaFeita = null;
          c.alvo = null;
          replanejar(id);
        }
        if(!c.visita && c.fila.length) {replanejar(id);ativo=true;}
        if (!c.caminho.length) return;
        ativo = true;
        let resta = (VELOCIDADE * Math.min(dt, 100)) / 1000;
        while (resta > 0 && c.caminho.length) {
          const p = c.caminho[0];
          const dx = p.x - c.pos.x;
          const dy = p.y - c.pos.y;
          const d = Math.hypot(dx, dy);
          if (d > 1e-6) c.direcao = dx + dy;
          if (d <= resta) {
            c.pos = { x: p.x, y: p.y };
            c.caminho.shift();
            resta -= d;
            c.distancia += d;
          } else {
            c.pos = { x: c.pos.x + (dx / d) * resta, y: c.pos.y + (dy / d) * resta };
            c.distancia += resta;
            resta = 0;
          }
        }
        if (!c.caminho.length) {
          if (c.visita) {
            c.pausaAte = t + (c.visita.tipo === 'trabalhar' ? 1600 : PAUSA_COORDENADOR);
            c.visitaFeita = c.visita;
          } else {
            c.carregando = false;
          }
        }
      });
      return ativo;
    }

    // Pose para o desenho.
    function corpo(id) {
      const c = corpos[id];
      if (!c) return null;
      const parado = !c.caminho.length && !c.pausaAte;
      if (c.alvo && c.alvo.tipo === "mesa" && !c.caminho.length) return { pose: "mesa", x: c.pos.x, y: c.pos.y, chave: c.pos.x + c.pos.y };
      if (parado && c.alvo && c.alvo.tipo === "assento") {
        return { pose: "sentado", x: c.pos.x, y: c.pos.y, z: c.alvo.assento.z, chave: c.alvo.assento.chave };
      }
      const vista = c.pausaAte ? "costas" : parado ? "frente" : c.direcao > 0 ? "frente" : "costas";
      return { pose: "pe", x: c.pos.x, y: c.pos.y, vista, chave: c.pos.x + c.pos.y + 0.05,
               passo: !parado && !c.pausaAte && !reduzido && Math.floor(c.distancia / 0.3) % 2 === 1, carregando: c.carregando && !reduzido };
    }

    return { caminhantes, sincronizar, avancar, corpo, _corpos: corpos };
  }

  // ================================================================ motor da cena
  function criar(canvas, camada, app) {
    const ctx = canvas.getContext("2d");
    canvas.width = LARGURA;
    canvas.height = ALTURA;
    const palco = canvas.closest(".palco");
    const fixos = objetosFixos();
    const reduzido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const grade = criarGrade(ocupacoes(fixos));
    // horário de carregamento (em segundos inteiros, como os horários do servidor): eventos anteriores não são animados
    const caminhada = criarCaminhada(app, grade, reduzido, Math.floor(Date.now() / 1000) * 1000);
    let escala = 1;
    let zoom = 1;
    const controles = document.createElement('div'); controles.className='zoom-escritorio';
    controles.setAttribute('aria-label','Tamanho do escritório');
    const textoZoom = document.createElement('span');
    [['−','Diminuir escritório',()=>{zoom=Math.max(1,zoom-0.15);}], ['Ajustar','Mostrar escritório inteiro',()=>{zoom=1;}], ['+','Aumentar escritório',()=>{zoom=Math.min(2.2,zoom+0.15);}]].forEach(([texto,rotulo,acao])=>{
      const b=document.createElement('button');b.type='button';b.textContent=texto;b.setAttribute('aria-label',rotulo);
      b.addEventListener('click',()=>{acao();posicionar();});controles.append(b);
    });
    // Os controles ficam na área do escritório (fora do conteúdo rolável do palco), à esquerda do painel do Supervisor
    // quando ele está aberto: nunca sobre o painel nem sobre os painéis da lateral esquerda.
    controles.append(textoZoom);(palco.parentElement || palco).append(controles);
    let quadroAnterior = -1;
    let tAnterior = null;
    const cache = {};
    const elementos = {};

    // Camada fixa (paredes, piso, sombras) em um canvas separado.
    function camadaFixa(noite) {
      if (cache[noite]) return cache[noite];
      const c = document.createElement("canvas");
      c.width = LARGURA;
      c.height = ALTURA;
      const g = c.getContext("2d");
      desenharParedes(g, noite);
      desenharPiso(g);
      if (!noite) {
        [7.75, 10.95, 14.15, 17.35, 1.0].forEach((x) => luzJanela(g, "y", x, x + (x === 1.0 ? 1.8 : 2.0)));
        luzJanela(g, "x", 8.2, 10.6);
      }
      const sombras = fixos.map((o) => o.sombra).filter(Boolean)
        .concat(Object.values(POSTOS).map((p) => [p.mesa.x, p.mesa.y, p.mesa.w, p.mesa.d]));
      sombras.forEach(([x, y, w, d]) => {
        poligono(g, [iso(x + 0.08, y + 0.12), iso(x + w + 0.22, y + 0.12), iso(x + w + 0.22, y + d + 0.24), iso(x + 0.08, y + d + 0.24)], "rgba(45, 28, 12, 0.2)");
      });
      Object.values(POSTOS).concat(VAGAS).forEach((p) => {
        const [cx, cy] = iso(p.pessoa.x, p.pessoa.y);
        bolha(g, cx, cy, 9, "rgba(45, 28, 12, 0.22)", 0.5);
      });
      cache[noite] = c;
      return c;
    }

    // Ponto do personagem no piso e "altura equivalente" para balão, seta e botão (sentado na copa fica mais baixo).
    function pontoDe(id) {
      const corpo = caminhada.corpo(id);
      if (!corpo) {
        const p = POSTOS[id].pessoa;
        const [ax, ay] = iso(p.x, p.y);
        return { x: p.x, y: p.y, ax, ay, topo: ay };
      }
      const [ax, ay] = iso(corpo.x, corpo.y);
      if (corpo.pose !== "sentado") return { x: corpo.x, y: corpo.y, ax, ay, topo: ay };
      const [, az] = iso(corpo.x, corpo.y, corpo.z);
      return { x: corpo.x, y: corpo.y, ax, ay, topo: Math.round(az + 3 - SPRITE_SENTADO.length * ESC_PESSOA) + TOPO_CABECA };
    }

    // botões de seleção (acessíveis) e etiquetas de hover/seleção
    app.agentes.forEach((ag) => {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "alvo";
      botao.dataset.agente = ag.id;
      botao.addEventListener("click", () => app.selecionar(ag.id));
      const etiqueta = document.createElement("div");
      etiqueta.className = "etiqueta";
      etiqueta.setAttribute("aria-hidden", "true");
      const mostrar = (v) => () => etiqueta.classList.toggle("hover", v);
      botao.addEventListener("mouseenter", mostrar(true));
      botao.addEventListener("mouseleave", mostrar(false));
      botao.addEventListener("focus", mostrar(true));
      botao.addEventListener("blur", mostrar(false));
      camada.append(botao, etiqueta);
      elementos[ag.id] = { botao, etiqueta };
    });

    // placas fixas das áreas (parede da fileira norte, parede da copa, piso da faixa sul)
    const placas = {};
    Object.entries(PLACAS).forEach(([id, cfg]) => {
      if (id !== "copa" && !app.agentes.some((a) => a.id === id)) return;
      const d = document.createElement("div");
      d.className = "placa-posto" + (cfg.breve ? " breve" : "") + (cfg.copa ? " copa" : "") + (cfg.piso ? " piso" : " parede")
        + (cfg.esquerda ? " esquerda" : "");
      d.setAttribute("aria-hidden", "true");
      d.dataset.placa = id;
      d.textContent = cfg.texto;
      camada.appendChild(d);
      placas[id] = d;
    });

    // quadro da área (Contabilidade): especialistas internos; abre o painel da área
    const quadros = {};
    app.areas.forEach((area) => {
      const q = document.createElement("button");
      q.type = "button";
      q.className = "quadro-area";
      q.dataset.area = area.id;
      q.addEventListener("click", () => app.selecionar(area.id));
      camada.appendChild(q);
      quadros[area.id] = q;
    });

    function posicionarAgente(id) {
      const p = POSTOS[id];
      const pt = pontoDe(id);
      const { botao, etiqueta } = elementos[id];
      Object.assign(botao.style, {
        left: (pt.ax - 16) * escala + "px",
        top: (pt.topo - TOPO_CABECA - 20) * escala + "px",
        width: 32 * escala + "px",
        height: (TOPO_CABECA + 24) * escala + "px"
      });
      const [ex, ey] = iso(pt.x + p.etiqueta, pt.y + p.etiqueta);
      Object.assign(etiqueta.style, { left: ex * escala + "px", top: (ey + 1 - (pt.ay - pt.topo)) * escala + "px" });
    }

    function posicionar() {
      const livreL = palco.clientWidth - 24;
      const livreA = palco.clientHeight - 12;
      escala = Math.max(0.1, Math.min(livreL / LARGURA, (livreA - 32) / ALTURA)) * zoom;
      palco.classList.toggle('zoom-manual',zoom>1);
      textoZoom.textContent=Math.round(zoom*100)+'%';
      const l = Math.round(LARGURA * escala);
      const a = Math.round(ALTURA * escala);
      for (const el of [canvas, camada, canvas.parentElement]) {
        el.style.width = l + "px";
        el.style.height = a + "px";
      }
      // texto das placas acompanha a escala da cena (mesma proporção em qualquer janela)
      camada.style.setProperty("--escala-cena", String(escala));
      app.agentes.forEach((ag) => posicionarAgente(ag.id));
      Object.entries(placas).forEach(([id, d]) => {
        const cfg = PLACAS[id];
        const [px, py] = cfg.piso ? iso(cfg.piso.x, cfg.piso.y) : cfg.paredeEsq !== undefined ? iso(0, cfg.paredeEsq, PAREDE + 4) : iso(cfg.parede, 0, PAREDE + 4);
        Object.assign(d.style, { left: px * escala + "px", top: py * escala + "px" });
      });
      app.areas.forEach((area) => {
        const { x, y } = AREAS[area.id].quadro;
        const [qx, qy] = iso(x, y);
        Object.assign(quadros[area.id].style, { left: qx * escala + "px", top: qy * escala + "px" });
      });
    }

    function atualizarRotulos() {
      app.agentes.forEach((ag) => {
        const est = app.estadoDe(ag.id);
        const info = EV.ESTADOS[est.status];
        const { botao, etiqueta } = elementos[ag.id];
        const sel = app.selecionado === ag.id;
        botao.setAttribute("aria-label", `${ag.nome}: ${info.rotulo}` + (est.disponibilidade ? ` · ${est.disponibilidade}` : ""));
        botao.setAttribute("aria-pressed", sel ? "true" : "false");
        etiqueta.classList.toggle("selecionada", sel);
        etiqueta.textContent = "";
        const nome = document.createElement("span");
        nome.className = "etiqueta-nome";
        nome.textContent = ag.nomeCurto;
        const chip = document.createElement("span");
        chip.className = "etiqueta-status";
        chip.style.setProperty("--cor-estado", info.cor);
        chip.textContent = `${info.simbolo} ${info.rotulo}`;
        etiqueta.append(nome, chip);
      });
      app.areas.forEach((area) => {
        const q = quadros[area.id];
        q.textContent = "";
        q.setAttribute("aria-pressed", app.selecionado === area.id ? "true" : "false");
        q.classList.toggle("selecionado", app.selecionado === area.id);
        // compacto: nome da área e especialistas ativos; a lista completa (e os "em breve") fica no painel da área
        const titulo = document.createElement("span");
        titulo.className = "quadro-titulo";
        titulo.textContent = `3 · ${area.nome}`;
        const linha = document.createElement("span");
        linha.className = "quadro-linha";
        linha.textContent = (area.especialistas || []).filter((e) => e.agente).map((e) => {
          const ag = app.agentes.find((a) => a.id === e.agente);
          return ag ? `${EV.ESTADOS[app.estadoDe(ag.id).status].simbolo} ${ag.nomeCurto}` : "";
        }).filter(Boolean).join(" · ");
        q.append(titulo, linha);
        q.setAttribute("aria-label", `Área ${area.nome}: ${q.textContent}`);
      });
    }

    function desenhar(t) {
      const dt = tAnterior === null ? 0 : t - tAnterior;
      tAnterior = t;
      const andando = !reduzido && caminhada.avancar(dt, t);
      const quadro = reduzido ? 0 : Math.floor(t / 160);
      if (quadro === quadroAnterior && !andando) return;
      quadroAnterior = quadro;
      if (andando) caminhada.caminhantes.forEach(posicionarAgente);

      const noite = app.agentes.filter((a) => a.implementado).every((a) => app.estadoDe(a.id).status === "OFFLINE");
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, LARGURA, ALTURA);
      ctx.drawImage(camadaFixa(noite), 0, 0);
      relogioParede(ctx, new Date());

      // anel de seleção no piso
      if (app.selecionado && POSTOS[app.selecionado]) {
        const { x, y } = pontoDe(app.selecionado);
        const r = 0.8;
        const pts = [iso(x - r, y), iso(x, y - r), iso(x + r, y), iso(x, y + r)];
        ctx.save();
        ctx.globalAlpha = reduzido ? 0.9 : 0.6 + 0.35 * Math.abs(Math.sin(t / 400));
        ctx.strokeStyle = COR.selecao;
        ctx.lineWidth = 2;
        ctx.beginPath();
        pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
        ctx.closePath();
        ctx.stroke();
        ctx.restore();
      }

      // halos de atenção no piso (aguardando, pendência, erro), onde o personagem estiver
      app.agentes.forEach((ag) => {
        const p = pontoDe(ag.id);
        halo(ctx, app.estadoDe(ag.id).status, p.x, p.y, t, reduzido);
      });

      // objetos ordenados por profundidade (de trás para a frente)
      const lista = fixos.slice();
      app.agentes.forEach((ag) => {
        const p = POSTOS[ag.id];
        const est = app.estadoDe(ag.id);
        const m = p.mesa;
        const corpo = caminhada.corpo(ag.id);
        lista.push({
          chave: m.x + m.w / 2 + m.y + m.d / 2,
          fn: (c) => {
            if (p.vista === "costas") {
              const estacao = ESTACOES[ag.id];
              mesaTrabalho(c, m);
              if (estacao && est.status !== "NAO_IMPLEMENTADO") estacao.antes(c, m);
              monitorFrente(c, m.x + 0.3, m.y + 0.18, desenharTela(c, est.status, quadro));
              teclado(c, m.x + 1.05, m.y + 0.66);
              if (estacao && est.status !== "NAO_IMPLEMENTADO") estacao.depois(c, m);
              if (est.pasta) pastaNaMesa(c, m.x + 1.6, m.y + 0.1, ag.id === "documentos" ? 20 : 11, est.pasta_bloqueada);
            } else {
              // mesa executiva do coordenador
              caixa(c, m.x, m.y, 0, m.w, m.d, 11, COR.nogueira);
              faceY(c, m.y + m.d, m.x + 0.15, m.x + m.w - 0.15, 2, 9, escurecer(COR.nogueira.esq, 0.12));
              faceY(c, m.y + m.d, m.x + m.w / 2 - 0.35, m.x + m.w / 2 + 0.35, 6, 8, COR.ouro.esq);
              faceZ(c, m.x + 0.6, m.y + 0.35, m.x + 2.2, m.y + 1.05, 11, "#3d5a48");
              caixa(c, m.x + 0.75, m.y + 0.12, 11, 1.1, 0.12, 13, COR.monitor);
              caixa(c, m.x + 1.2, m.y + 0.2, 11, 0.2, 0.15, 2, COR.monitor, false);
              pilhaPapel(c, m.x + 2.3, m.y + 0.6, 4);
              caixa(c, m.x + 0.25, m.y + 0.75, 11, 0.25, 0.3, 2, tons("#2b2f36"), false); // telefone
              // luminária
              caixa(c, m.x + 2.85, m.y + 0.25, 11, 0.2, 0.2, 1, COR.ouro, false);
              caixa(c, m.x + 2.92, m.y + 0.32, 12, 0.06, 0.06, 10, COR.ouro, false);
              caixa(c, m.x + 2.75, m.y + 0.2, 21, 0.38, 0.32, 4, tons("#2f4a3a"), false);
              if (est.pasta) pastaNaMesa(c, m.x + 1.95, m.y + 0.45, 11, est.pasta_bloqueada);
            }
          }
        });
        if (corpo && corpo.pose !== "mesa") {
          // personagem fora do posto: cadeira vazia na mesa
          lista.push({ chave: p.pessoa.x + p.pessoa.y, fn: (c) => {
            const [sx, sy] = origemSprite(...iso(p.pessoa.x, p.pessoa.y));
            desenharSprite(c, SPRITE_COSTAS, PALETA_BASE, sx, sy, { de: LINHA_CADEIRA });
          } });
        }
        lista.push({ chave: corpo ? corpo.chave : p.pessoa.x + p.pessoa.y, fn: (c) => desenharAgente(c, ag, est, quadro, reduzido, corpo) });
      });
      lista.sort((a, b) => a.chave - b.chave).forEach((o) => o.fn(ctx));

      // iluminação ambiente: vinheta suave e, à noite, escurecimento
      ctx.save();
      ctx.globalCompositeOperation = "source-atop";
      const v = ctx.createRadialGradient(LARGURA * 0.5, ALTURA * 0.55, ALTURA * 0.25, LARGURA * 0.5, ALTURA * 0.55, LARGURA * 0.62);
      v.addColorStop(0, "rgba(255, 244, 220, 0.05)");
      v.addColorStop(1, "rgba(30, 18, 8, 0.22)");
      ctx.fillStyle = v;
      ctx.fillRect(0, 0, LARGURA, ALTURA);
      if (noite) {
        ctx.fillStyle = "rgba(10, 14, 30, 0.45)";
        ctx.fillRect(0, 0, LARGURA, ALTURA);
      }
      ctx.restore();
      LUZES.forEach((l) => {
        const [lx, ly] = iso(l.x, l.y, l.z);
        brilho(ctx, lx, ly, l.raio * (noite ? 1.6 : 1), "rgba(255, 214, 150, A)", noite ? 0.32 : 0.16);
      });

      // balões e indicadores por cima de tudo (seguem o personagem)
      app.agentes.forEach((ag) => {
        const est = app.estadoDe(ag.id);
        const { ax, topo } = pontoDe(ag.id);
        if (est.status !== "NAO_IMPLEMENTADO") desenharBalao(ctx, est.status, ax, topo, quadro, reduzido);
        if (est.status === "CONCLUIDO" && !reduzido) brilhos(ctx, ax, topo, quadro);
        if (app.selecionado === ag.id) seta(ctx, ax, est.status === "NAO_IMPLEMENTADO" ? topo + 12 : topo, t, reduzido);
      });
    }

    function laco(t) {
      desenhar(t);
      window.requestAnimationFrame(laco);
    }

    if (window.ResizeObserver) new ResizeObserver(posicionar).observe(palco);
    window.addEventListener("resize", posicionar);
    app.aoMudar(() => {
      caminhada.sincronizar();
      quadroAnterior = -1;
      atualizarRotulos();
      posicionar();
    });
    caminhada.sincronizar();
    posicionar();
    atualizarRotulos();
    window.requestAnimationFrame(laco);

    const cena = {
      focar(id) {
        const alvo = elementos[id] ? elementos[id].botao : quadros[id];
        if (alvo) alvo.focus();
      },
      // Somente leitura, para os testes: retângulos das placas e dos personagens e polígonos dos móveis (px da tela).
      _geometria() {
        const base = camada.getBoundingClientRect();
        const ret = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - base.left, y: r.top - base.top, w: r.width, h: r.height }; };
        const caixaTela = ([x, y, w, d], h) => [[x, y], [x + w, y], [x + w, y + d], [x, y + d]].flatMap(([a, b]) => [iso(a, b, 0), iso(a, b, h)])
          .map(([px, py]) => [px * escala, py * escala]);
        return {
          placas: Object.fromEntries(Object.entries(placas).map(([id, d]) => [id, ret(d)]).concat(Object.entries(quadros).map(([id, q]) => [id, ret(q)]))),
          alvos: Object.fromEntries(Object.entries(elementos).map(([id, e]) => [id, ret(e.botao)])),
          moveis: fixos.filter((o) => o.sombra).map((o) => caixaTela(o.sombra, 30))
            .concat(Object.values(POSTOS).map((p) => caixaTela([p.mesa.x, p.mesa.y, p.mesa.w, p.mesa.d], 26)))
        };
      },
      _pastas() {
        return app.agentes.filter((a) => app.estadoDe(a.id).pasta).map((a) => ({ agente: a.id, bloqueada: !!app.estadoDe(a.id).pasta_bloqueada }));
      },
      // Somente leitura, para os testes: onde cada personagem está e se está andando.
      _posicoes() {
        const r = {};
        caminhada.caminhantes.forEach((id) => {
          const c = caminhada._corpos[id];
          const corpo = caminhada.corpo(id);
          r[id] = { x: +c.pos.x.toFixed(2), y: +c.pos.y.toFixed(2), pose: corpo.pose, alvo: c.alvo && c.alvo.tipo,
                    andando: c.caminho.length > 0 || !!c.pausaAte || c.fila.length > 0, visita: c.visita && c.visita.destino,
                    destino: c.alvo && c.alvo.destino, carregando: !!corpo.carregando,
                    restante: c.caminho.map((p) => ({ x: +p.x.toFixed(2), y: +p.y.toFixed(2) })) };
        });
        return r;
      }
    };
    return cena;
  }

  // Posição do balão de estado (px lógicos) no posto, usada pelos testes para conferir o indicador no canvas.
  const posicaoBalao = (id) => {
    const [ax, ay] = iso(POSTOS[id].pessoa.x, POSTOS[id].pessoa.y);
    return [Math.round(ax - 6), Math.round(ay - TOPO_CABECA - 18)];
  };

  EV.cena = {
    criar,
    _interno: {
      SPRITE_COSTAS, SPRITE_FRENTE, GLIFOS, POSTOS, VAGAS, AREAS, COPA, VISITA_COORDENADOR, ENTREGA, BALAO, LARGURA, ALTURA, posicaoBalao,
      CELULA, FOLGA, grade: () => criarGrade(ocupacoes(objetosFixos())), planejarCaminho, ehLivre, celulaDe, iso, criarCaminhada
    }
  };
})();
