"""
Calcula o albedo medio de uma area urbana.
Uso: python albedo_urbano.py imagem.bmp dados_inmet.csv
"""

import struct
import csv
import sys
import os


def ler_bmp(caminho_bmp):
    with open(caminho_bmp, "rb") as f:
        dados = f.read()

    assinatura = dados[0:2]
    if assinatura != b"BM":
        raise ValueError("Arquivo nao e um BMP valido (assinatura 'BM' ausente).")

    offset_pixels = struct.unpack_from("<I", dados, 10)[0]

    tamanho_dib = struct.unpack_from("<I", dados, 14)[0]
    largura = struct.unpack_from("<i", dados, 18)[0]
    altura_bruta = struct.unpack_from("<i", dados, 22)[0]
    bits_por_pixel = struct.unpack_from("<H", dados, 28)[0]
    compressao = struct.unpack_from("<I", dados, 30)[0]

    if compressao not in (0, 3):
        raise ValueError(
            "Este script so le BMP sem compressao (BI_RGB) ou BI_BITFIELDS. "
            "Compressao encontrada: %d" % compressao
        )

    if bits_por_pixel not in (16, 24, 32):
        raise ValueError(
            "Este script so le BMP de 16, 24 ou 32 bits por pixel. "
            "Encontrado: %d bits." % bits_por_pixel
        )

    # Mascaras de cor (BI_BITFIELDS) ficam logo apos o cabecalho de 40 bytes
    if compressao == 3:
        mascara_r = struct.unpack_from("<I", dados, 54)[0]
        mascara_g = struct.unpack_from("<I", dados, 58)[0]
        mascara_b = struct.unpack_from("<I", dados, 62)[0]
    elif bits_por_pixel == 16:
        mascara_r, mascara_g, mascara_b = 0x7C00, 0x03E0, 0x001F
    else:
        mascara_r, mascara_g, mascara_b = 0x00FF0000, 0x0000FF00, 0x000000FF

    def extrair(valor, mascara):
        if mascara == 0:
            return 0
        deslocamento = (mascara & -mascara).bit_length() - 1
        maximo = mascara >> deslocamento
        return ((valor & mascara) >> deslocamento) * 255 // maximo

    de_baixo_pra_cima = altura_bruta > 0
    altura = abs(altura_bruta)
    bytes_por_pixel = bits_por_pixel // 8

    tamanho_linha_sem_padding = largura * bytes_por_pixel
    tamanho_linha = ((tamanho_linha_sem_padding + 3) // 4) * 4

    pixels = [None] * (largura * altura)

    for linha in range(altura):
        linha_arquivo = (altura - 1 - linha) if de_baixo_pra_cima else linha
        inicio_linha = offset_pixels + linha_arquivo * tamanho_linha

        for coluna in range(largura):
            pos = inicio_linha + coluna * bytes_por_pixel
            if bits_por_pixel == 24:
                b = dados[pos]
                g = dados[pos + 1]
                r = dados[pos + 2]
            else:
                valor = int.from_bytes(dados[pos:pos + bytes_por_pixel], "little")
                r = extrair(valor, mascara_r)
                g = extrair(valor, mascara_g)
                b = extrair(valor, mascara_b)

            indice_pixel = linha * largura + coluna
            pixels[indice_pixel] = (r, g, b)

    return largura, altura, pixels


def luminancia(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def calcular_albedo_visual(pixels):
    if not pixels:
        raise ValueError("Lista de pixels vazia.")

    soma_luminancia = 0.0
    for (r, g, b) in pixels:
        soma_luminancia += luminancia(r, g, b)

    media_luminancia = soma_luminancia / len(pixels)
    albedo_visual = media_luminancia / 255.0
    return albedo_visual


def ler_radiacao_inmet(caminho_csv, delimitador=";"):
    with open(caminho_csv, "r", encoding="latin-1") as f:
        leitor = csv.reader(f, delimiter=delimitador)
        linhas = list(leitor)

    indice_cabecalho = None
    indice_coluna_radiacao = None

    for i, linha in enumerate(linhas):
        for j, celula in enumerate(linha):
            if "RADIACAO" in celula.upper() or "RADIAÇÃO" in celula.upper():
                indice_cabecalho = i
                indice_coluna_radiacao = j
                break
        if indice_cabecalho is not None:
            break

    if indice_cabecalho is None:
        raise ValueError(
            "Nao foi encontrada nenhuma coluna com 'RADIACAO' no cabecalho "
            "do arquivo CSV do INMET. Verifique o arquivo."
        )

    valores = []
    for linha in linhas[indice_cabecalho + 1:]:
        if len(linha) <= indice_coluna_radiacao:
            continue
        valor_texto = linha[indice_coluna_radiacao].strip().replace(",", ".")
        if valor_texto == "" or valor_texto == "-9999":
            continue
        try:
            valor = float(valor_texto)
        except ValueError:
            continue
        valores.append(valor)

    if not valores:
        raise ValueError("Nenhum valor de radiacao valido encontrado no CSV.")

    media_radiacao = sum(valores) / len(valores)
    return media_radiacao


def calcular_albedo_estimado(albedo_visual, radiacao_incidente_media):
    radiacao_refletida_estimada = radiacao_incidente_media * albedo_visual
    albedo_estimado = radiacao_refletida_estimada / radiacao_incidente_media
    return albedo_estimado, radiacao_refletida_estimada


def calcular_albedo_real(radiacao_refletida_medida, radiacao_incidente_medida):
    if radiacao_incidente_medida == 0:
        raise ValueError("Radiacao incidente nao pode ser zero.")
    return radiacao_refletida_medida / radiacao_incidente_medida


def main():
    caminho_bmp = "area_urbana.bmp"
    caminho_csv_inmet = "dados_inmet.csv"

    if len(sys.argv) >= 3:
        caminho_bmp = sys.argv[1]
        caminho_csv_inmet = sys.argv[2]

    if not os.path.isfile(caminho_bmp):
        print("ERRO: arquivo BMP nao encontrado:", caminho_bmp)
        return
    if not os.path.isfile(caminho_csv_inmet):
        print("ERRO: arquivo CSV do INMET nao encontrado:", caminho_csv_inmet)
        return

    print("Lendo imagem BMP:", caminho_bmp)
    largura, altura, pixels = ler_bmp(caminho_bmp)
    print("  Dimensoes: %d x %d pixels (%d pixels no total)" % (largura, altura, len(pixels)))

    albedo_visual = calcular_albedo_visual(pixels)
    print("  Albedo visual medio (0-1): %.4f" % albedo_visual)

    print("\nLendo dados do INMET:", caminho_csv_inmet)
    radiacao_media = ler_radiacao_inmet(caminho_csv_inmet)
    print("  Radiacao global media: %.2f Kj/m2" % radiacao_media)

    albedo_estimado, radiacao_refletida_estimada = calcular_albedo_estimado(
        albedo_visual, radiacao_media
    )

    print("\n===== RESULTADO =====")
    print("Albedo visual (indice da imagem):       %.4f" % albedo_visual)
    print("Radiacao incidente media (INMET):       %.2f Kj/m2" % radiacao_media)
    print("Radiacao refletida estimada:            %.2f Kj/m2" % radiacao_refletida_estimada)


if __name__ == "__main__":
    main()
