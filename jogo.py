"""Regras do Fuga Lógica: distância, tempo, níveis, vidas, obstáculos, vitória e derrota.

O tempo é medido aqui, no Python: ele começa quando o sinal é entregue ao
navegador e termina quando a resposta chega. O navegador apenas mostra o
que o servidor decide.
"""

import json
import random
import time
from pathlib import Path

import logica

PASTA_DADOS = Path(__file__).parent / "dados"


def carregar_config():
    with open(PASTA_DADOS / "config.json", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def carregar_banco():
    with open(PASTA_DADOS / "proposicoes.json", encoding="utf-8") as arquivo:
        return json.load(arquivo)["sinais"]


# ---------------------------------------------------------------------------
# Correção dos sinais (usa o motor lógico)
# ---------------------------------------------------------------------------

def _opcao_correta(sinal, texto):
    criterio = sinal.get("criterio")
    if sinal["tipo"] == "argumento":
        return logica.argumento_valido(sinal["premissas"], texto)
    if criterio == "tautologia":
        return logica.e_tautologia(texto)
    if criterio == "contradicao":
        return logica.e_contradicao(texto)
    if criterio == "equivalente":
        return logica.equivalentes(sinal["referencia"], texto)
    raise ValueError(f"Critério desconhecido no sinal {sinal['id']}: {criterio}")


def opcoes_corretas(sinal):
    """Índices das opções corretas de um sinal de escolha ou de argumento."""
    return [i for i, texto in enumerate(sinal["opcoes"]) if _opcao_correta(sinal, texto)]


def solucoes_satisfazer(sinal):
    """Todas as atribuições das variáveis livres que tornam a fórmula verdadeira."""
    fixas = {v: val for v, val in sinal["variaveis"].items() if val is not None}
    livres = [v for v, val in sinal["variaveis"].items() if val is None]
    return [
        linha
        for linha in logica.atribuicoes(livres)
        if logica.avaliar(sinal["formula"], {**fixas, **linha})
    ]


# ---------------------------------------------------------------------------
# Obstáculos (níveis avançados)
#
# Antes de alguns sinais aparece um obstáculo na pista. Ele só sai do caminho
# depois que o jogador responde uma pergunta rápida. As perguntas são geradas
# na hora e corrigidas pelo motor lógico, então não há gabarito guardado.
# ---------------------------------------------------------------------------

OBSTACULO_DO_NIVEL = {3: "cones", 4: "barreira", 5: "pedras"}
TITULO_OBSTACULO = {
    "cones": "Cones na pista",
    "barreira": "Barreira na rodovia",
    "pedras": "Pedras na estrada",
}

# Fórmulas das perguntas "qual é o valor?", da mais simples à mais difícil.
FORMULAS_VALOR = {
    3: ["P & Q", "P | Q", "~P", "P -> Q", "~P | Q", "~(P & Q)"],
    4: ["P <-> Q", "~P -> Q", "~(P | Q)", "P & ~Q", "(P -> Q) & P", "~P <-> Q"],
    5: ["(P & Q) -> R", "P | (Q & R)", "(P -> Q) | R", "~(P & R) <-> Q", "(P | Q) & ~R"],
}

# Perguntas de negação: proposição base e opções (só uma é a negação dela).
NEGACOES = [
    ("P & Q", ["~P | ~Q", "~P & ~Q", "~P & Q"]),
    ("P | Q", ["~P & ~Q", "~P | ~Q", "P & ~Q"]),
    ("P -> Q", ["P & ~Q", "~P -> ~Q", "Q -> P"]),
    ("~P | Q", ["P & ~Q", "P | ~Q", "~P & Q"]),
]

# Tipos de pergunta liberados em cada nível.
PERGUNTAS_DO_NIVEL = {
    3: ["valor"],
    4: ["valor", "valor", "linhas"],
    5: ["valor", "negacao", "linhas"],
}


def _nivel_obstaculo(nivel):
    return max(3, min(5, nivel))


def gerar_obstaculo(nivel, sorteio):
    """Cria um obstáculo com uma pergunta rápida adequada ao nível."""
    n = _nivel_obstaculo(nivel)
    tipo = OBSTACULO_DO_NIVEL[n]
    pergunta = sorteio.choice(PERGUNTAS_DO_NIVEL[n])
    base = {
        "id": f"obs-{n}-{pergunta}",
        "nivel": nivel,
        "tipo": "obstaculo",
        "obstaculo": tipo,
        "titulo": TITULO_OBSTACULO[tipo],
        "pergunta": pergunta,
        "embaralhar": True,
    }

    if pergunta == "valor":
        formula = sorteio.choice(FORMULAS_VALOR[n])
        valores = {v: sorteio.choice([True, False]) for v in logica.variaveis(formula)}
        resultado = logica.avaliar(formula, valores)
        return {
            **base,
            "enunciado": f"Para tirar o obstáculo: com {logica.descrever(valores)}, "
                         "qual é o valor desta proposição?",
            "formula": formula,
            "valores": valores,
            "opcoes": ["Verdadeira (V)", "Falsa (F)"],
            "certa": 0 if resultado else 1,
            "embaralhar": False,
        }

    if pergunta == "linhas":
        qtd = sorteio.choice([3, 4, 5])
        return {
            **base,
            "enunciado": f"Para tirar o obstáculo: uma proposição tem {qtd} variáveis. "
                         "Quantas linhas tem a tabela-verdade dela?",
            "quantidade": qtd,
            "opcoes": [str(2 ** qtd), str(2 * qtd), str(2 ** (qtd + 1))],
            "certa": 0,
        }

    proposicao, opcoes = sorteio.choice(NEGACOES)
    negada = f"~({proposicao})"
    certa = next(i for i, o in enumerate(opcoes) if logica.equivalentes(negada, o))
    return {
        **base,
        "enunciado": "Para tirar o obstáculo: qual opção é a negação desta proposição?",
        "formula": proposicao,
        "opcoes": list(opcoes),
        "certa": certa,
    }


def explicar_obstaculo(s):
    """Explicação mostrada quando o jogador erra a pergunta do obstáculo."""
    if s["pergunta"] == "valor":
        resultado = "verdadeira" if s["certa"] == 0 else "falsa"
        return (f"Com {logica.descrever(s['valores'])}, "
                f"{logica.formatar(s['formula'])} é {resultado}.")
    if s["pergunta"] == "linhas":
        n = s["quantidade"]
        return f"São 2^{n} = {2 ** n} linhas: cada variável dobra o número de combinações."
    certa = logica.formatar(s["opcoes"][s["certa"]])
    return (f"A negação de {logica.formatar(s['formula'])} é {certa} "
            "(lembre das leis de De Morgan e de que ¬(P → Q) ≡ P ∧ ¬Q).")


# ---------------------------------------------------------------------------
# Partida
# ---------------------------------------------------------------------------

class Partida:
    def __init__(self, config, banco, relogio=time.monotonic, sorteio=None):
        self.config = config
        self.banco = banco
        self.relogio = relogio
        self.sorteio = sorteio or random.Random()

        self.distancia = float(config["distancia_inicial"])
        self.nivel = 1
        self.resolvidos = 0
        self.erros = 0
        self.situacao = "jogando"  # jogando | vitoria | derrota
        self.vidas_max = int(config.get("vidas", 3))
        self.vidas = self.vidas_max
        self.alcances = 0  # quantas vezes a viatura chegou no carro
        self.obstaculos_superados = 0
        self._obstaculo_pendente = False

        self.sinal = None
        self.ordem = []  # ordem embaralhada das opções mostradas
        self.inicio_sinal = None
        self.ultimo_desconto = None
        self._usados = set()

    # -- tempo -------------------------------------------------------------

    def _descontar_tempo(self, agora):
        """Enquanto o carro está parado, a viatura se aproxima."""
        if self.sinal is None or self.situacao != "jogando":
            return
        decorrido = agora - self.ultimo_desconto
        self.ultimo_desconto = agora
        self.distancia -= decorrido * self.config["aproximacao_m_por_s"]
        if self.distancia <= 0:
            self._ser_alcancado()

    def _ser_alcancado(self):
        """A viatura chegou no carro: perde uma vida. Sem vidas, o jogador é pego."""
        self.alcances += 1
        self.vidas -= 1
        if self.vidas <= 0:
            self.vidas = 0
            self.distancia = 0
            self.situacao = "derrota"
        else:
            # O carro escapa por pouco e volta a fugir com uma pequena vantagem.
            self.distancia = float(self.config.get("distancia_apos_alcance", 35))

    def velocidade(self):
        """Velocidade do carro do jogador (km/h): cresce a cada nível."""
        tabela = self.config.get("velocidade_por_nivel_kmh") or [80]
        return tabela[min(self.nivel, len(tabela)) - 1]

    def _bonus(self, segundos, nivel):
        extra = self.config["acrescimo_tempo_por_nivel"] * (nivel - 1)
        for faixa in self.config["bonus_por_tempo"]:
            if segundos <= faixa["ate_segundos"] + extra:
                return faixa["metros"]
        return 0

    # -- sinais ------------------------------------------------------------

    def _sortear_sinal(self):
        candidatos = [s for s in self.banco if s["nivel"] == self.nivel]
        novos = [s for s in candidatos if s["id"] not in self._usados]
        if not novos:  # acabaram os sinais do nível: recomeça a fila
            self._usados -= {s["id"] for s in candidatos}
            novos = candidatos
        escolhido = self.sorteio.choice(novos)
        self._usados.add(escolhido["id"])
        return escolhido

    def proximo_sinal(self):
        """Entrega o sinal atual (sorteia um novo se não houver) e inicia o cronômetro."""
        if self.situacao != "jogando":
            return None
        if self.sinal is None:
            if self._obstaculo_pendente:
                self._obstaculo_pendente = False
                self.sinal = gerar_obstaculo(self.nivel, self.sorteio)
            else:
                self.sinal = self._sortear_sinal()
            self.ordem = list(range(len(self.sinal.get("opcoes", []))))
            if self.sinal.get("embaralhar", True):
                self.sorteio.shuffle(self.ordem)
            self.inicio_sinal = self.ultimo_desconto = self.relogio()
        return self._publico()

    def _publico(self):
        """Dados do sinal que o navegador pode ver (nunca a resposta)."""
        s = self.sinal
        dados = {
            "id": s["id"],
            "nivel": s["nivel"],
            "tipo": s["tipo"],
            "enunciado": s["enunciado"],
        }
        if s["tipo"] == "obstaculo":
            dados["obstaculo"] = s["obstaculo"]
            dados["titulo"] = s["titulo"]
            if "formula" in s:
                dados["formula"] = logica.formatar(s["formula"])
            dados["opcoes"] = [logica.formatar(s["opcoes"][i]) for i in self.ordem]
        elif s["tipo"] == "satisfazer":
            dados["formula"] = logica.formatar(s["formula"])
            dados["variaveis"] = [
                {"nome": nome, "valor": valor, "livre": valor is None}
                for nome, valor in s["variaveis"].items()
            ]
        else:
            if "referencia" in s:
                dados["referencia"] = logica.formatar(s["referencia"])
            if "premissas" in s:
                dados["premissas"] = [logica.formatar(p) for p in s["premissas"]]
            dados["opcoes"] = [logica.formatar(s["opcoes"][i]) for i in self.ordem]
        return dados

    # -- estado ------------------------------------------------------------

    def atualizar(self):
        """Aplica o tempo que passou e devolve o estado atual."""
        self._descontar_tempo(self.relogio())
        return self.estado()

    def estado(self):
        segundos = 0.0
        bonus = 0
        if self.sinal is not None and self.situacao == "jogando":
            segundos = self.relogio() - self.inicio_sinal
            if self.sinal["tipo"] != "obstaculo":
                bonus = self._bonus(segundos, self.sinal["nivel"])
        return {
            "situacao": self.situacao,
            "distancia": round(self.distancia, 1),
            "meta": self.config["meta_vitoria"],
            "nivel": self.nivel,
            "resolvidos": self.resolvidos,
            "erros": self.erros,
            "vidas": self.vidas,
            "vidas_max": self.vidas_max,
            "alcances": self.alcances,
            "velocidade": self.velocidade(),
            "obstaculos_superados": self.obstaculos_superados,
            "segundos_no_sinal": round(segundos, 1),
            "bonus_atual": bonus,
        }

    # -- resposta ----------------------------------------------------------

    def responder(self, valores=None, escolha=None):
        if self.situacao != "jogando" or self.sinal is None:
            raise RuntimeError("Não há sinal aguardando resposta.")

        agora = self.relogio()
        self._descontar_tempo(agora)
        if self.situacao == "derrota":
            return self._resultado(False, "A viatura te pegou enquanto você pensava.")

        correto, explicacao = self._corrigir(valores, escolha)

        if not correto:
            self.erros += 1
            self.distancia -= self.config["penalidade_erro"]
            if self.distancia <= 0:
                self._ser_alcancado()
            return self._resultado(False, explicacao)

        if self.sinal["tipo"] == "obstaculo":
            self.obstaculos_superados += 1
            self.sinal = None
            return self._resultado(True, "Obstáculo superado! Pista livre.")

        bonus = self._bonus(agora - self.inicio_sinal, self.sinal["nivel"])
        self.distancia += bonus
        self.resolvidos += 1
        self.nivel = min(
            self.config["nivel_maximo"],
            1 + self.resolvidos // self.config["sinais_por_nivel"],
        )
        self.sinal = None
        if self.distancia >= self.config["meta_vitoria"]:
            self.situacao = "vitoria"
        else:
            # Nos níveis avançados, pode surgir um obstáculo antes do próximo sinal.
            chances = self.config.get("chance_obstaculo_por_nivel", {})
            chance = chances.get(str(self.nivel), 0)
            self._obstaculo_pendente = self.sorteio.random() < chance
        texto = f"Sinal aberto! +{bonus} m" if bonus else "Sinal aberto, mas sem bônus de tempo."
        return self._resultado(True, texto, bonus)

    def _resultado(self, correto, mensagem, bonus=0):
        return {
            "correto": correto,
            "mensagem": mensagem,
            "bonus": bonus,
            "estado": self.estado(),
        }

    def _corrigir(self, valores, escolha):
        s = self.sinal
        if s["tipo"] == "satisfazer":
            return self._corrigir_satisfazer(valores)
        return self._corrigir_escolha(escolha)

    def _corrigir_satisfazer(self, valores):
        s = self.sinal
        valores = valores or {}
        atribuicao = {}
        for nome, fixo in s["variaveis"].items():
            if fixo is not None:
                atribuicao[nome] = fixo
            else:
                if not isinstance(valores.get(nome), bool):
                    raise ValueError(f"Falta o valor da variável {nome}.")
                atribuicao[nome] = valores[nome]
        if logica.avaliar(s["formula"], atribuicao):
            return True, ""
        return False, (
            f"Com {logica.descrever(atribuicao)}, a condição "
            f"{logica.formatar(s['formula'])} fica falsa."
        )

    def _corrigir_escolha(self, escolha):
        s = self.sinal
        if not isinstance(escolha, int) or not 0 <= escolha < len(self.ordem):
            raise ValueError("Escolha uma das opções.")
        if s["tipo"] == "obstaculo":
            if self.ordem[escolha] == s["certa"]:
                return True, ""
            return False, explicar_obstaculo(s)
        texto = s["opcoes"][self.ordem[escolha]]
        if _opcao_correta(s, texto):
            return True, ""
        return False, self._explicar_erro(s, texto)

    @staticmethod
    def _explicar_erro(s, texto):
        mostrada = logica.formatar(texto)
        criterio = s.get("criterio")
        if s["tipo"] == "argumento":
            linha = logica.contraexemplo_argumento(s["premissas"], texto)
            return (
                f"Com {logica.descrever(linha)}, as premissas são verdadeiras "
                f"e {mostrada} é falsa: o argumento não é válido."
            )
        if criterio == "tautologia":
            linha = logica.linha_falsa(texto)
            return f"{mostrada} não é tautologia: com {logica.descrever(linha)} ela é falsa."
        if criterio == "contradicao":
            linha = next(l for l, r in logica.tabela_verdade(texto) if r)
            return f"{mostrada} não é contradição: com {logica.descrever(linha)} ela é verdadeira."
        linha = logica.contraexemplo_equivalencia(s["referencia"], texto)
        return f"{mostrada} não é equivalente: com {logica.descrever(linha)} os valores diferem."
