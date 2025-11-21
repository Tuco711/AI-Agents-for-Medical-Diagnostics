from textual.app import App, ComposeResult
from textual.widgets import DirectoryTree, Label, Header, Footer

class SelecionadorArquivo(App):

    CSS = """
        DirectoryTree {
            border: solid green;
        }
        Label {
            padding: 1;
            background: $accent;
            color: auto;
            width: 100%;
        }
"""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Navegue e pressione ENTER para selecionar um arquivo", id="status")
        # Inicia a árvore no diretório atual "./"
        yield DirectoryTree("./")
        yield Footer()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        # O evento carrega o caminho do arquivo selecionado
        caminho = event.path
        self.query_one("#status").update(f"Selecionado: {caminho}")

        # Aqui você faria algo com o arquivo e poderia fechar o app
        self.exit(caminho)
        return caminho

def select_file(start_path: str = "./"):
    """
    Executa o seletor e retorna o caminho selecionado (ou None se fechado sem seleção).
    Importante: chama app.run() que retorna o valor passado a self.exit(...)
    """
    app = SelecionadorArquivo()
    # opcional: ajustar caminho inicial (se desejar suportar start_path)
    # app._path = start_path  # não necessário para Textual DirectoryTree padrão
    result = app.run()
    return result

if __name__ == "__main__":
    caminho = select_file()
    if caminho is not None:
        print(caminho)
    else:
        # nenhum arquivo selecionado
        print("")