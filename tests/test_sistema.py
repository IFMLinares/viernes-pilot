"""Tests unitarios para las utilidades de herramientas del sistema."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.sistema import normalizar_texto, buscar_coincidencias


class TestSistemaTools(unittest.TestCase):
    
    def test_normalizacion_texto(self):
        """Valida que los acentos, mayúsculas y caracteres especiales se limpien correctamente."""
        self.assertEqual(normalizar_texto("Calculadora de Windows!!!"), "calculadora de windows")
        self.assertEqual(normalizar_texto("Música y Videos"), "musica y videos")
        self.assertEqual(normalizar_texto("  Spotify  "), "spotify")
        self.assertEqual(normalizar_texto("Google Chrome (Beta)"), "google chrome beta")
        self.assertEqual(normalizar_texto("Visual Studio Code - Insiders"), "visual studio code insiders")
    
    def test_buscar_coincidencias_exactas_y_fuzzy(self):
        """Valida las búsquedas exactas, difusas y por subcadena."""
        # Mock de base de datos de aplicaciones
        candidatos = {
            "calculadora de windows": ("Calculadora de Windows", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
            "calculadora grafica": ("Calculadora gráfica", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!AppGr"),
            "spotify": ("Spotify", "Spotify.App"),
            "google chrome": ("Google Chrome", "chrome.lnk"),
            "bloc de notas": ("Bloc de notas", "notepad")
        }
        
        # 1. Coincidencia exacta
        res = buscar_coincidencias("spotify", candidatos)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][0], "spotify")
        self.assertGreaterEqual(res[0][1], 0.9)
        
        # 2. Coincidencia con acento y mayúsculas
        res = buscar_coincidencias("Música", {
            "musica": ("Música", "music.exe")
        })
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][0], "musica")
        
        # 3. Coincidencia con error de escritura (typo)
        res = buscar_coincidencias("calcualdora", candidatos)
        self.assertTrue(len(res) > 0)
        # Debería coincidir con alguna calculadora
        self.assertIn(res[0][0], ["calculadora de windows", "calculadora grafica"])
        
        # 4. Coincidencia por subcadena
        res = buscar_coincidencias("calculadora", candidatos)
        # Debería dar alta prioridad a las calculadoras
        self.assertTrue(len(res) >= 2)
        nombres = [item[0] for item in res]
        self.assertIn("calculadora de windows", nombres)
        self.assertIn("calculadora grafica", nombres)

    def test_to_windows_path(self):
        """Valida que la ruta de Windows se traduzca correctamente si estamos en WSL."""
        from tools.sistema import is_wsl, to_windows_path
        if not is_wsl():
            self.assertEqual(to_windows_path("/home/test"), "/home/test")
        else:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            win_path = to_windows_path(current_dir)
            self.assertTrue(win_path.startswith("\\\\wsl") or "Ubuntu" in win_path or "localhost" in win_path)


if __name__ == "__main__":
    unittest.main()

