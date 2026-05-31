# -*- coding: utf-8 -*-
"""recompile_protos.py - Script utilitário para compilar arquivos Protobuf do ecossistema 1Crypten.

Esse script executa o compilador grpc_tools.protoc utilizando as bibliotecas instaladas no
ambiente ativo do Python (evitando problemas de incompatibilidade de versão runtime/gencode)
e aplica um patch corretivo nos caminhos de importação gerados nos stubs do gRPC.
"""

import os
import sys
import subprocess

def recompile():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    protos_dir = os.path.join(backend_dir, "protos")
    services_dir = os.path.join(backend_dir, "services")
    proto_file = os.path.join(protos_dir, "hermes.proto")

    print("[PROTO-COMPILER] Iniciando compilacao do Protobuf...")
    print(f"  - Diretorio de Protos: {protos_dir}")
    print(f"  - Destino dos Stubs: {services_dir}")
    print(f"  - Arquivo de Entrada: {proto_file}")

    if not os.path.exists(proto_file):
        print(f"[PROTO-COMPILER] Erro: Arquivo proto nao encontrado em {proto_file}")
        sys.exit(1)

    # Invoca o protoc do grpc_tools instalado no Python ativo
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{protos_dir}",
        f"--python_out={services_dir}",
        f"--grpc_python_out={services_dir}",
        proto_file
    ]

    print(f"[PROTO-COMPILER] Executando comando: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("[PROTO-COMPILER] Arquivos hermes_pb2.py e hermes_pb2_grpc.py gerados com SUCESSO!")
    except subprocess.CalledProcessError as e:
        print("[PROTO-COMPILER] Erro ao compilar com protoc:")
        print(e.stderr)
        sys.exit(1)

    grpc_stub_path = os.path.join(services_dir, "hermes_pb2_grpc.py")
    if os.path.exists(grpc_stub_path):
        print(f"[PROTO-COMPILER] Aplicando patch de importacoes em {grpc_stub_path}...")
        with open(grpc_stub_path, "r", encoding="utf-8") as f:
            content = f.read()

        target_import = "import hermes_pb2 as hermes__pb2"
        replacement_import = "import services.hermes_pb2 as hermes__pb2"
        
        if target_import in content:
            content = content.replace(target_import, replacement_import)
            with open(grpc_stub_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("[PROTO-COMPILER] Patch de importacao gRPC aplicado com sucesso!")
        else:
            print("[PROTO-COMPILER] Patch nao necessario ou ja aplicado.")

if __name__ == "__main__":
    recompile()
