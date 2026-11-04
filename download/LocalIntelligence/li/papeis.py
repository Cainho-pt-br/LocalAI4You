"""Funções (papéis) que um modelo local pode ter no dia a dia, e como a nota de cada uma é composta.

É a camada que traduz "MMLU-PT 87,5%" em "serve para conversar em português?". Os pesos são
decisão de projeto (ver cerebro/papeis-e-pesos.md) e podem ser mudados aqui sem refazer testes.
"""
from __future__ import annotations

from typing import Dict, List

# suítes: mmlu_pt, mmlu_pro, capitu, ifeval, bfcl_prompt, bfcl_native, humaneval, gsm8k, visao
PAPEIS: List[dict] = [
    {
        "id": "chat_pt", "rotulo": "Assistente do dia a dia (português)", "icone": "💬",
        "descricao": "Conversar, explicar, redigir e resumir em português brasileiro.",
        "pesos": {"mmlu_pt": 0.35, "capitu": 0.35, "ifeval": 0.15, "mmlu_pro": 0.15},
        "ctx_alvo": 16384, "onde": "Open WebUI, LM Studio, chat do Bionic",
    },
    {
        "id": "codigo", "rotulo": "Programação e agente de código", "icone": "👨‍💻",
        "descricao": "Escrever e editar código, rodar em IDE/terminal (Bionic, OpenCode, Roo Code).",
        "pesos": {"humaneval": 0.45, "bfcl_native": 0.20, "ifeval": 0.10, "gsm8k": 0.10, "mmlu_pro": 0.15},
        "ctx_alvo": 32768, "exige": ["tools"], "onde": "Bionic, OpenCode, VS Code (Roo Code)",
        "nota": "HumanEval mede só funções Python curtas — é indício, não prova, de que edita repositórios reais.",
    },
    {
        "id": "agente", "rotulo": "Agentes e chamada de ferramentas", "icone": "🛠️",
        "descricao": "Escolher a ferramenta certa e preencher os argumentos (automação, MCP, fluxos).",
        "pesos": {"bfcl_native": 0.50, "bfcl_prompt": 0.20, "ifeval": 0.15, "capitu": 0.15},
        "ctx_alvo": 16384, "exige": ["tools"], "onde": "Agentes próprios, n8n, scripts com a API do Ollama",
    },
    {
        "id": "regras", "rotulo": "Extração, JSON e seguir regras", "icone": "📋",
        "descricao": "Cumprir formato e restrições à risca (extrair dados, gerar JSON, redação formal).",
        "pesos": {"ifeval": 0.40, "capitu": 0.40, "bfcl_prompt": 0.20},
        "ctx_alvo": 8192, "onde": "Automações, pipelines do parque (ETL de leads, classificação)",
    },
    {
        "id": "raciocinio", "rotulo": "Raciocínio e análise difícil", "icone": "🧠",
        "descricao": "Lógica, matemática e perguntas de conhecimento técnico mais duras.",
        "pesos": {"mmlu_pro": 0.40, "gsm8k": 0.40, "mmlu_pt": 0.20},
        "ctx_alvo": 16384, "onde": "Consultoria técnica, estudo, revisão de decisões",
    },
    {
        "id": "rapido", "rotulo": "Segundo plano e tarefas rápidas", "icone": "⚡",
        "descricao": "Pequeno e veloz, para rodar ao lado de jogo/edição e em lote (triagem, resumos).",
        "pesos": {"mmlu_pt": 0.30, "ifeval": 0.30, "capitu": 0.20, "gsm8k": 0.20},
        "ctx_alvo": 8192, "onde": "Scripts em segundo plano via API do Ollama",
        "nota": "Nota = qualidade; o painel só considera 'rápido' quem também é pequeno (≤ 5 GB) e veloz.",
    },
    {
        "id": "visao", "rotulo": "Ler imagens e documentos", "icone": "👁️",
        "descricao": "Entender prints, gráficos, notas fiscais e painéis visuais (Moondream, Qwen-VL, Gemma 4…).",
        "pesos": {"visao": 0.5, "visao_leve": 0.5}, "ctx_alvo": 8192, "exige": ["vision"], "sem_nota": False,   # `visao_leve` é o teste justo para modelos pequenos; quem só tem um dos dois usa o que tem
        "onde": "Open WebUI, LM Studio, OCR e inspeção de tela",
        "nota": "Mede leitura de notas fiscais (OCR), gráficos de barras e extração JSON de painéis visuais.",
    },
]

POR_ID: Dict[str, dict] = {p["id"]: p for p in PAPEIS}

SUITES = {
    "mmlu_pt": "MMLU-PT (conhecimento, português)",
    "mmlu_pro": "MMLU-Pro (conhecimento difícil, inglês)",
    "capitu": "CAPITU (instruções em português)",
    "ifeval": "IFEval (formato e restrições)",
    "bfcl_prompt": "BFCL — ferramenta via JSON no prompt",
    "bfcl_native": "BFCL — ferramenta nativa (API tools)",
    "humaneval": "HumanEval (código Python que passa nos testes)",
    "gsm8k": "GSM8K (problemas de matemática)",
    "visao": "Visão (OCR de notas, gráficos de barras e painéis)",
    "visao_leve": "Visão leve (contar, cor, forma, posição, ler número) — modelos pequenos",
    "visao_fotos": "Visão em fotos suas (contagem) × detector atual",
}


def pesos_do_papel(papel_id: str) -> Dict[str, float]:
    return dict(POR_ID[papel_id].get("pesos", {}))
