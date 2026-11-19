/* Interface do Fuga Lógica.
 * O navegador só mostra e envia: quem corrige as respostas, mede o tempo,
 * controla as vidas e decide vitória ou derrota é o servidor Python
 * (app.py, jogo.py, logica.py).
 */
(() => {
  'use strict';

  const $ = (seletor) => document.querySelector(seletor);
  const cena = $('#cena');
  const carro = $('#carro');
  const viatura = $('#viatura');
  const semaforo = $('#semaforo');
  const obstaculo = $('#obstaculo');
  const placa = $('#placa');
  const medidor = $('#medidor');
  const enchimento = $('#enchimento');
  const pausa = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

  // Nome de cada cenário (um por nível).
  const CENARIOS = {
    1: 'Entardecer no campo',
    2: 'Cidade à noite',
    3: 'Deserto escaldante',
    4: 'Serra nevada',
    5: 'Tempestade neon',
  };
  const VELOCIDADE_BASE = 80;     // km/h do nível 1 (multiplicador 1 na animação)
  const VELOCIDADE_MAXIMA = 200;  // fundo de escala do velocímetro

  let meta = 400;
  let sinal = null;          // desafio exibido no momento (sinal ou obstáculo)
  let valores = {};          // interruptores escolhidos (tipo "satisfazer")
  let escolha = null;        // opção marcada (escolha, argumento e obstáculo)
  let enviando = false;
  let sondagem = null;
  let ultimoEstado = null;
  let nivelNaTela = 1;       // nível cujo cenário está sendo exibido
  let alcancesVistos = 0;    // quantos alcances da viatura já foram animados
  let animandoAlcance = false;
  let elementoNaPista = semaforo;  // semáforo ou obstáculo parado à frente

  /* ---------- Comunicação com o servidor ---------- */

  async function api(url, corpo) {
    const opcoes = corpo === undefined ? {} : {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
    };
    const resposta = await fetch(url, opcoes);
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(dados.erro || 'Falha na comunicação com o servidor.');
    return dados;
  }

  /* ---------- Cena, medidor, vidas e velocidade ---------- */

  function posicionar(distancia) {
    const largura = cena.clientWidth;
    const larguraViatura = viatura.offsetWidth;
    const carroX = Math.min(largura * 0.58, largura - carro.offsetWidth - 96);
    const escala = (carroX + 30) / Math.min(meta, 200);  // escala visual limitada
    const recuo = Math.min(distancia * escala, carroX + 40);
    carro.style.left = carroX + 'px';
    viatura.style.transform = `translateX(${carroX - larguraViatura - recuo + 30}px)`;
  }

  function desenharVidas(estado, quebrar) {
    const caixa = $('#vidas');
    caixa.replaceChildren();
    for (let i = 0; i < estado.vidas_max; i++) {
      const coracao = document.createElement('span');
      const viva = i < estado.vidas;
      coracao.className = 'coracao' + (viva ? '' : ' perdida') +
        (quebrar && i === estado.vidas ? ' quebrando' : '');
      coracao.textContent = viva ? '♥' : '♡';
      caixa.appendChild(coracao);
    }
    caixa.setAttribute('aria-label', `Vidas restantes: ${estado.vidas} de ${estado.vidas_max}`);
  }

  function mostrarVelocidade(kmh) {
    $('#vel-num').textContent = kmh;
    const angulo = -70 + 140 * Math.min(1, kmh / VELOCIDADE_MAXIMA);
    $('#ponteiro').style.transform = `rotate(${angulo}deg)`;
  }

  function aplicarCenario(nivel, kmh) {
    nivelNaTela = nivel;
    cena.dataset.cenario = String(Math.min(nivel, 5));
    cena.style.setProperty('--vel', (kmh / VELOCIDADE_BASE).toFixed(2));
    mostrarVelocidade(kmh);
  }

  function atualizarHud(estado) {
    ultimoEstado = estado;
    meta = estado.meta;
    const distancia = Math.max(0, estado.distancia);
    $('#dist-num').textContent = Math.round(distancia);
    $('#nivel-num').textContent = estado.nivel;
    enchimento.style.width = Math.min(100, (distancia / meta) * 100) + '%';
    medidor.setAttribute('aria-valuenow', String(Math.round(distancia)));
    document.body.classList.toggle('perigo', distancia < 20);

    if (estado.alcances > alcancesVistos) {
      alcancesVistos = estado.alcances;
      animarAlcance(estado);
    } else if (!animandoAlcance) {
      desenharVidas(estado, false);
      posicionar(distancia);
    }

    const cronometro = $('#cronometro');
    if (cronometro && sinal) {
      cronometro.querySelector('.segundos').textContent =
        estado.segundos_no_sinal.toFixed(1).replace('.', ',');
      const bonus = cronometro.querySelector('.bonus');
      if (bonus) {
        bonus.textContent = estado.bonus_atual > 0 ? `+${estado.bonus_atual} m` : 'sem bônus';
      }
    }
  }

  /* A viatura chega no carro: perde uma vida e o carro escapa por pouco. */
  async function animarAlcance(estado) {
    animandoAlcance = true;
    posicionar(0);
    cena.classList.remove('alcance');
    void cena.offsetWidth;
    cena.classList.add('alcance');
    desenharVidas(estado, true);

    if (estado.situacao === 'derrota') return;  // a tela final cuida do resto

    const restam = estado.vidas;
    $('#aviso-alcance-texto').textContent = restam === 1
      ? 'Você escapou por pouco. Última vida: na próxima, você é pego!'
      : `Você escapou por pouco. Restam ${restam} vidas.`;
    $('#faixa-nivel').hidden = true;
    $('#aviso-alcance').hidden = false;
    await pausa(1500);
    $('#aviso-alcance').hidden = true;
    cena.classList.remove('alcance');
    animandoAlcance = false;
    if (ultimoEstado) posicionar(Math.max(0, ultimoEstado.distancia));
  }

  /* ---------- Movimento ---------- */

  function trazerParaPista(dados) {
    const el = dados.tipo === 'obstaculo' ? obstaculo : semaforo;
    if (el === obstaculo) obstaculo.dataset.tipo = dados.obstaculo;
    else semaforo.dataset.luz = 'vermelha';
    if (el.dataset.fase !== 'parado') {
      el.dataset.fase = 'fora';
      void el.offsetWidth;  // aplica o estado "fora" antes de entrar
      el.dataset.fase = 'parado';
    }
    elementoNaPista = el;
  }

  async function trocarCenario(estado) {
    const transicao = $('#transicao');
    transicao.classList.add('ativa');
    await pausa(450);
    aplicarCenario(estado.nivel, estado.velocidade);
    $('#faixa-nivel-titulo').textContent = `Nível ${estado.nivel} · ${CENARIOS[Math.min(estado.nivel, 5)]}`;
    $('#faixa-nivel-texto').textContent = estado.nivel >= 3
      ? `${estado.velocidade} km/h · atenção: obstáculos na pista!`
      : `O carro acelerou: ${estado.velocidade} km/h`;
    transicao.classList.remove('ativa');
    $('#faixa-nivel').hidden = false;
    setTimeout(() => { $('#faixa-nivel').hidden = true; }, 2200);
  }

  async function dirigir(estado) {
    cena.classList.add('andando');
    const saindo = elementoNaPista;
    // O obstáculo já sumiu da pista (fase "liberado"); o semáforo passa por trás do carro.
    if (saindo === semaforo) saindo.dataset.fase = 'saindo';
    const subiuDeNivel = estado.nivel > nivelNaTela;
    if (subiuDeNivel) {
      await pausa(500);
      await trocarCenario(estado);
      await pausa(400);
    } else {
      await pausa(1100);
    }
    saindo.dataset.fase = 'fora';
  }

  async function parar() {
    await pausa(900);
    cena.classList.remove('andando');
  }

