# Qwen: mesure locale du 27 octobre 2026

Machine : RTX 5060 Laptop GPU, 8 151 Mio de VRAM, environ 32 Gio de RAM.
ComfyUI 0.42.1, PyTorch 2.14.0+cu130. Tests séquentiels, sans autre génération en concurrence.

## Résultats

| Essai | Durée totale | Pic VRAM global échantillonné |
| --- | ---: | ---: |
| Génération initiale, encodeur CPU, 28 étapes | 230 s | 5 128 Mio |
| Encodeur GPU avec déchargement partiel en RAM, 28 étapes | 58 s | 5 606 Mio |
| Répétition du même essai | 57 s | 5 448 Mio |
| Même configuration, cache Qwen automatique | 59 s | 5 448 Mio |
| Même configuration, 20 étapes | 46 s | 5 448 Mio |
| Retouche avec encodeur CPU | 282 s | 5 290 Mio |
| Même retouche avec encodeur GPU | 68 s | 5 450 Mio |
| Autre prompt, paysage 768 × 512, encodeur GPU, 28 étapes | 76 s | 5 418 Mio |

Les essais comparés utilisent la même seed (8765), le même prompt, les mêmes poids
et une résolution de 512 × 512. La retouche utilise exactement la même image de référence.
Les durées incluent le traitement de la requête et l’enregistrement, avec interrogation
de l’historique toutes les deux secondes. Elles excluent le démarrage du serveur.
Le premier essai Qwen suit une génération FLUX ; les suivants ne constituent pas
un protocole de démarrage à froid du système d’exploitation.

## Changement retenu

- Retirer `--lowvram` du démarrage ComfyUI pour permettre l’exécution GPU de l’encodeur.
- Utiliser `device=default` dans le chargeur de texte Qwen et son workflow exporté.
- Conserver `--disable-dynamic-vram --reserve-vram 1 --cache-none`.
- Conserver le cache Qwen sur CPU, les 28 étapes, la résolution et les poids actuels.

Les logs confirment environ 4,7 Gio d’encodeur sur GPU avec le reste en RAM,
puis le modèle de génération entièrement chargé sur GPU pendant l’échantillonnage.
L’ensemble du pipeline ne reste donc pas simultanément en VRAM.
Le test CPU de retouche utilise le serveur sans `--lowvram`, mais force explicitement
l’encodeur sur CPU comme dans le workflow initial.

## Qualité et limites

La comparaison visuelle ne montre pas de dégradation notable sur la génération
et la retouche comparées. Les pixels ne sont pas identiques : l’écart absolu moyen
est de 1,38/255 en génération et 0,34/255 en retouche. Ces mesures de proximité
ne sont pas une évaluation générale de qualité. La retouche présente une accentuation
marquée des textures dans les deux versions.

Les 20 étapes changent davantage le rendu pour un gain supplémentaire limité ; elles
ne sont pas retenues. Le cache automatique n’apporte pas de gain mesurable ici.
La résolution et la quantification ne sont pas réduites : l’objectif de vitesse est
atteint sans ces compromis et sans télécharger de nouveaux poids.

Les pics mémoire sont échantillonnés, pas une garantie de plafond absolu. Les prompts,
formats, autres applications et conditions thermiques peuvent modifier ces résultats.
Les mesures brutes et le script local sont dans `.tools/qwen_benchmark/` (ignoré par Git).
Les images de comparaison sont dans `ComfyUI/output/BenchQwen/`.

## Vérifications complémentaires

Une génération SD 1.5 et une génération FLUX Schnell ont réussi avec le nouveau
profil partagé, sans erreur mémoire (respectivement 20 s et 101 s, non comparés
à un essai de référence chronométré). Les 32 tests automatisés ont réussi.
L’encodeur FLUX reste explicitement sur CPU dans son workflow.
