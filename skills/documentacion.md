# Estándar de Documentación del Proyecto / Project Documentation Standard

[Español](#espanol) | [English](#english)

---

## Español

Este documento establece las directrices obligatorias para la documentación de **Viernes Pilot**. Cualquier agente o desarrollador que modifique o extienda la documentación del proyecto debe cumplir con estas pautas de estilo y estructura.

### 1. Tono y Estilo
- **Tono Profesional**: La redacción debe ser seria, clara y técnica.
- **Evitar Iconos/Emojis**: No se permite el uso de emojis o iconos informales (ej. 🚀, 🧠, 🤖, etc.) en los encabezados ni en el cuerpo del texto para conservar un diseño sobrio y profesional.

### 2. Estructura Modular
- ** README Principal**: Los archivos `README.md` y `README.es.md` en la raíz del repositorio solo deben actuar como puertas de entrada, resumiendo requisitos previos, pasos de instalación, comandos de ejecución y enlazando a los submódulos.
- **Sub-READMEs de Módulos**: Cada directorio principal debe contar con sus propios archivos de documentación:
  - `core/`: Detalla el funcionamiento de los clientes de IA (Ollama) y base de datos de memoria (Engram).
  - `tools/`: Explica el comportamiento de los scripts de sistema (lanzador fuzzy, integración de terminales).
  - `tests/`: Detalla la cobertura y comandos para correr las pruebas unitarias y de integración.

### 3. Soporte Bilingüe
- Todos los documentos deben mantenerse en versiones gemelas en inglés y español.
- El archivo en inglés debe llamarse `README.md` y el de español `README.es.md`.
- En el encabezado de cada archivo, debe incluirse un menú de selección de idioma bidireccional:
  ```markdown
  [English](README.md) | [Español](README.es.md)
  ```

---

## English

This document defines the mandatory guidelines for the documentation of **Viernes Pilot**. Any agent or developer modifying or extending the project's documentation must adhere to these style and structural rules.

### 1. Tone and Style
- **Professional Tone**: The writing style must be clean, precise, and technical.
- **No Emojis/Icons**: Do not use casual emojis or icons (e.g., 🚀, 🧠, 🤖, etc.) in headers or body text to maintain a clean and professional appearance.

### 2. Modular Structure
- **Main README**: The root `README.md` and `README.es.md` files must act solely as entry points, highlighting prerequisites, installation steps, execution commands, and linking to submodules.
- **Sub-module READMEs**: Each primary folder must contain its own documentation files:
  - `core/`: Explains the operation of AI clients (Ollama) and the memory database (Engram).
  - `tools/`: Details system tools (fuzzy launcher, terminal integration).
  - `tests/`: Outlines test coverage and execution commands.

### 3. Bilingual Support
- Every document must be kept in matching English and Spanish editions.
- English files must be named `README.md` and Spanish files `README.es.md`.
- Every file header must contain a bidirectional language switcher menu:
  ```markdown
  [English](README.md) | [Español](README.es.md)
  ```
