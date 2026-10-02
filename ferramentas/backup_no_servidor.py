"""
Cópia de segurança no SERVIDOR da empresa e no DRIVE, rodada por este notebook (Agendador
de Tarefas do Windows: ao entrar no Windows e duas vezes por dia).

  1. lê a planilha e guarda a cópia numa pasta deste notebook (se algo mudou);
  2. leva para a pasta do servidor tudo que ainda não está lá;
  3. grava no Drive da empresa, se a cópia de lá estiver desatualizada. O robô da nuvem
     também grava no Drive: são dois caminhos de propósito, para o Drive não depender só
     do GitHub. Quem chega depois vê que a cópia já está lá e não duplica.

As pastas ficam em backup.local.json, na raiz do projeto (fora do git, porque o código
também vai para o repositório público da demonstração):
  {"pasta_notebook": "...", "pasta_servidor": "...", "chaves_drive": "..."}
"chaves_drive" é opcional: caminho de um secrets.toml que tenha drive_oauth_client_id,
drive_oauth_client_secret e drive_oauth_refresh_token (só é LIDO, na hora de rodar). Sem
ele, e sem essas chaves no secrets deste projeto, o passo do Drive é pulado.

Servidor fora do ar (notebook longe da empresa e sem Hamachi) não é erro: a cópia fica
no notebook e é entregue na próxima vez. Só aparece um aviso na tela se passarem
DIAS_SEM_AVISAR dias sem conseguir ler a planilha, entregar ao servidor ou gravar no
Drive, ou se a planilha encolher.

Rodar na mão:  py ferramentas\\backup_no_servidor.py          (mostra o que fez)
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import backup  # noqa: E402

with open(os.environ.get("COBRANCA_BACKUP_CONFIG", RAIZ / "backup.local.json"), encoding="utf-8") as _f:
    _CONFIG = json.load(_f)
BASE = Path(_CONFIG["pasta_notebook"])
PASTA_LOCAL = BASE / "copias"      # só isto vai para o servidor
PASTA_SERVIDOR = Path(_CONFIG["pasta_servidor"])
ESTADO = BASE / "estado.json"
REGISTRO = BASE / "registro.txt"
DIAS_SEM_AVISAR = 3

LEIA_ME = """BACKUP DAS COBRANÇAS VITHALL

Cada arquivo "AAAA-MM-DD HHhMM backup cobrancas" é a planilha de cobranças INTEIRA naquele momento.
  .xlsx  abre no Excel ou no Google Planilhas
  .json  o mesmo conteúdo, usado para reconstruir a planilha do app

Um arquivo novo só aparece quando algo mudou na planilha. Nenhum arquivo antigo é apagado.
ULTIMA_CONFERENCIA.txt mostra quando foi a última vez que a cópia foi conferida.

Existem mais duas cópias iguais a esta: no Drive da empresa (pasta BACKUP / BACKUP COBRANCAS)
e no GitHub (repositório privado do app, ramo "backup").

NÃO apague nem edite estes arquivos.
"""


def _ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _avisar_na_tela(texto: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, texto, "Backup das cobranças Vithall", 0x30)
    except Exception:
        pass


def _dias_desde(iso: str, agora: datetime) -> float:
    return (agora - datetime.fromisoformat(iso)).total_seconds() / 86400


def _chaves_drive(secrets: dict) -> dict | None:
    """Autorização do Drive: do secrets deste projeto ou do arquivo apontado em "chaves_drive"."""
    campos = ("client_id", "client_secret", "refresh_token")
    fontes = [secrets]
    if _CONFIG.get("chaves_drive"):
        with open(_CONFIG["chaves_drive"], "rb") as f:
            fontes.append(tomllib.load(f))
    for fonte in fontes:
        if all(fonte.get("drive_oauth_" + c) for c in campos):
            return {c: fonte["drive_oauth_" + c] for c in campos}
    return None


def main() -> int:
    agora = backup.agora_sp()
    PASTA_LOCAL.mkdir(parents=True, exist_ok=True)
    falas, erros = [], []

    with open(RAIZ / ".streamlit" / "secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    os.environ["GCP_SERVICE_ACCOUNT"] = json.dumps(dict(secrets["gcp_service_account"]))

    leia = PASTA_LOCAL / "LEIA-ME.txt"
    if not leia.exists() or leia.read_text(encoding="utf-8") != LEIA_ME:
        leia.write_text(LEIA_ME, encoding="utf-8")

    estado = _ler_estado()
    # Enquanto nunca deu certo, os dias sem backup contam a partir da primeira tentativa
    estado.setdefault("desde", agora.isoformat(timespec="seconds"))
    leu = entregou = False
    try:
        copia = backup.ler_planilha(secrets["spreadsheet_id"])
        leu = True
    except Exception as e:
        erros.append(f"não consegui ler a planilha: {type(e).__name__}: {e}")
    if leu:
        erros += backup.executar(copia, PASTA_LOCAL, saida=falas.append)
        if not erros:
            estado["leitura_ok"] = agora.isoformat(timespec="seconds")

    # O espelho roda mesmo sem leitura nova: entrega o que ficou guardado no notebook.
    try:
        if not PASTA_SERVIDOR.parent.exists():
            raise OSError("servidor fora do ar: sem rede da empresa nem Hamachi")
        levados = backup.espelhar(PASTA_LOCAL, PASTA_SERVIDOR)
        falas.append(f"Servidor: {levados} arquivo(s) levado(s) para {PASTA_SERVIDOR}")
        entregou = True
        estado["servidor_ok"] = agora.isoformat(timespec="seconds")
    except Exception as e:
        falas.append(f"Servidor: não entregue agora ({e}); fica guardado no notebook")

    # Drive: segundo caminho, além do robô da nuvem. Falhar aqui não é erro da rodada.
    conferir = [("leitura_ok", "ler a planilha"), ("servidor_ok", "entregar a cópia ao servidor")]
    try:
        chaves = _chaves_drive(secrets)
        if chaves is None:
            falas.append("Drive: sem autorização neste notebook, pulando")
        else:
            conferir.append(("drive_ok", "gravar a cópia no Drive"))
            if leu and not erros:
                nome, gravou = backup.enviar_drive(copia, backup.servico_drive(chaves))
                falas.append(f"Drive: {'cópia nova ' + nome if gravou else 'sem mudança desde ' + nome}")
                estado["drive_ok"] = agora.isoformat(timespec="seconds")
    except Exception as e:
        falas.append(f"Drive: não gravado agora ({type(e).__name__}: {e}); a nuvem cobre")

    avisar = [e for e in erros if "encolheu" in e]
    for chave, rotulo in conferir:
        dias = _dias_desde(estado.get(chave) or estado["desde"], agora)
        if dias >= DIAS_SEM_AVISAR:
            avisar.append(f"Faz {int(dias)} dias que o backup não consegue {rotulo}.")
    hoje = agora.strftime("%Y-%m-%d")
    if avisar and estado.get("avisou_em") != hoje:
        estado["avisou_em"] = hoje
        _avisar_na_tela("\n".join(avisar) + "\n\nAbra o Claude e peça para conferir o backup das cobranças.")

    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    linhas = [f"{agora.strftime('%d/%m/%Y %H:%M')} " + t for t in falas + ["ERRO: " + e for e in erros]]
    with open(REGISTRO, "a", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    if sys.stdout:   # pelo Agendador roda sem janela (pythonw): não há onde imprimir
        print("\n".join(linhas))
    return 0 if leu and entregou and not erros else 1


if __name__ == "__main__":
    sys.exit(main())
