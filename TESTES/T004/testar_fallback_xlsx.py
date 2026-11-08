"""Casos fictícios do fallback seguro para estilos XLSX inválidos."""
import hashlib, io, json, shutil, tempfile, unittest, zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "AGENTES/DOCUMENTOS/ferramentas"))
import extrair_documentos

FIX = Path(__file__).parents[1] / "FIXTURES-FICTICIAS/XLSX-FALLBACK/styles_invalido.xlsx"
NORMAL = Path(__file__).parents[1] / "FIXTURES-FICTICIAS/EMPRESA-TESTE/T004/XLSX/XLSX-01_extrato.xlsx"

class FallbackXlsx(unittest.TestCase):
    def test_01_normal_e_fallback(self):
        self.assertEqual(extrair_documentos.ler_planilha(NORMAL)["leitura"], "EXTRAIDO_PLANILHA")
        self.assertEqual(extrair_documentos.ler_planilha(FIX)["leitura"], "EXTRAIDO_PLANILHA")
        self.assertIn("LEITOR_CALAMINE_FALLBACK", extrair_documentos.ler_planilha(FIX)["marcacoes"])
    def test_02_dados_integros(self):
        d=extrair_documentos.ler_planilha(FIX); self.assertEqual(len(d["conteudo"]["abas"][0]["linhas"]),5); self.assertEqual(d["conteudo"]["abas"][0]["linhas"][0]["valores"][0],"Data")
    def test_03_nao_corrompido(self): self.assertNotEqual(extrair_documentos.ler_planilha(FIX)["leitura"],"ARQUIVO_CORROMPIDO")
    def test_04_marca_estilo(self): self.assertIn("ESTILO_XLSX_INVALIDO", extrair_documentos.ler_planilha(FIX)["marcacoes"])
    def test_05_zip_quebrado(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
            f.write(FIX.read_bytes()[:100]); f.flush()
            with self.assertRaises(extrair_documentos.Resultado) as ctx: extrair_documentos.ler_planilha(Path(f.name))
            self.assertEqual(ctx.exception.leitura,"ARQUIVO_CORROMPIDO")
    def test_06_worksheet_quebrada(self):
        b=io.BytesIO();
        with zipfile.ZipFile(FIX) as z, zipfile.ZipFile(b,"w") as out:
            for n in z.namelist(): out.writestr(n,b"<broken" if n.startswith("xl/worksheets/") else z.read(n))
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
            f.write(b.getvalue()); f.flush()
            with self.assertRaises(extrair_documentos.Resultado): extrair_documentos.ler_planilha(Path(f.name))
    def test_07_macro_marcada(self):
        macro=Path(__file__).parents[1] / "FIXTURES-FICTICIAS/EMPRESA-TESTE/T004/XLSX/XLSX-07_com_macro.xlsm"
        self.assertIn("CONTEM_MACROS", extrair_documentos.ler_planilha(macro)["marcacoes"])
    def test_08_links_nao_executados(self): self.assertEqual(extrair_documentos.ler_planilha(FIX)["conteudo"]["links_externos"],0)
    def test_09_formulas_nao_executadas(self): self.assertNotIn(600,[v for l in extrair_documentos.ler_planilha(FIX)["conteudo"]["abas"][0]["linhas"] for v in l["valores"]])
    def test_10_original_inalterado(self):
        antes=hashlib.sha256(FIX.read_bytes()).hexdigest(); extrair_documentos.ler_planilha(FIX); depois=hashlib.sha256(FIX.read_bytes()).hexdigest(); self.assertEqual(antes,depois)

if __name__ == "__main__": unittest.main(verbosity=2)
