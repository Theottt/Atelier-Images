# Atelier Images

Double-clique sur **Atelier Images.exe** à la racine du dossier portable.
Le lanceur démarre les serveurs en arrière-plan, sans console, puis ouvre ton navigateur par défaut
sur http://127.0.0.1:8189 une fois Atelier et ComfyUI disponibles. Un démarrage lent peut prendre
jusqu'à six minutes ; une boîte de dialogue signale un échec. Les serveurs déjà actifs sont réutilisés.
Plusieurs doubles-clics pendant le démarrage ne lancent pas plusieurs instances du lanceur.

L'exécutable est un lanceur : conserve-le avec `start.ps1`, `atelier_images`, `ComfyUI` et
`python_embeded`. Il ne contient ni les modèles ni Python. Fermer le navigateur ne termine pas
les serveurs, qui restent disponibles pour la prochaine ouverture.

### Recréer l'exécutable

Ouvre PowerShell à la racine du projet, puis exécute :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_launcher.ps1
```

La compilation utilise le compilateur C# du .NET Framework installé avec Windows, sans téléchargement.
Le code source est `atelier_images/launcher/Launcher.cs`. Le résultat est `Atelier Images.exe`,
avec une copie de compilation dans `build/launcher`. Ces fichiers générés sont ignorés par Git.
`ExecutionPolicy Bypass` concerne uniquement ce processus, sans modifier la configuration Windows.
L'exécutable produit n'est pas signé numériquement.

Le lancement par double-clic a été confirmé fonctionnel par l'utilisateur.
Certaines stratégies Windows peuvent néanmoins bloquer un exécutable non signé,
comme cela s'est produit dans le contexte de test automatisé. Dans ce cas, une autorisation
conforme à la stratégie ou une signature acceptée est nécessaire ; recompiler ne suffit pas.

Pour lancer le script manuellement depuis une console PowerShell :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Utilise l'exécutable pour l'ouverture sans fenêtre de console.
Le fichier `Lancer_Atelier_Images.bat` reste disponible comme ancien lanceur avec console.

Les diagnostics du nouveau lanceur sont dans `atelier_images/launcher.log`,
`atelier_images/launcher-server.stdout.log`, `atelier_images/launcher-server.stderr.log`
et `atelier_images/comfyui.log`. Les deux journaux `launcher-server` sont remplacés au prochain
nouveau démarrage du serveur ; `launcher.log` et `comfyui.log` sont alimentés à la suite.


1. Écris une description, en français ou en anglais.
2. Choisis Carré, Portrait ou Paysage.
3. Clique sur **Créer mon image**. Le premier chargement peut prendre quelques minutes.

Clique sur une image de la galerie pour l'agrandir, la télécharger ou reprendre sa description et sa seed.
Une seed vide produit une nouvelle variation. Avec la même seed, la même description et le même format, tu peux reproduire une composition.
Avec FLUX, chaque description crée une nouvelle image. Avec Qwen, tu peux aussi ajouter une image à retoucher.

Les PNG restent dans `ComfyUI/output` et contiennent le workflow ComfyUI. La galerie affiche les 150 dernières images de cet atelier et du test initial.
## Changer de modèle

Le menu **Mon modèle** permet de choisir un modèle installé. Ton choix reste mémorisé dans ce navigateur.
L'import de modèles dans l'interface a été retiré. Pour ajouter un modèle, demande son installation et sa configuration dans cette conversation.

FLUX Schnell conserve ses 4 étapes et ses encodeurs CLIP-L/T5. Le profil Dev utilise 20 étapes et une guidance de 3,5.

## Qwen Image 2.1 : génération et retouche

Sélectionne **Qwen Image 2.1 Uncensored · génération et retouche** dans **Mon modèle**.
Sans image de référence, décris l'image souhaitée, choisis le format et lance la génération.
Pour retoucher, ajoute une image PNG, JPEG ou WebP dans **Retoucher une image avec Qwen**, puis écris par exemple « Remplace le fond par un jardin ensoleillé ».
Clique sur **Retirer** pour revenir à la création à partir du texte seul.

La retouche accepte une référence à la fois (20 Mo et 25 mégapixels maximum). Une copie normalisée est conservée dans `ComfyUI/input` ; le fichier original est préservé.
Elle conserve les proportions de la référence, avec une surface proche de 512 × 512 pixels. Le sélecteur de format sert à la génération sans référence.
Qwen utilise 28 étapes et son encodeur Qwen3-VL sur CPU. Il peut prendre sensiblement plus de temps que FLUX Schnell, surtout au premier chargement.

Source choisie : https://huggingface.co/spaces/fishpasters/uncensored-imageTOimage2Ref
Poids locaux quantifiés : https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF
Modèle Q4_K_M, encodeur INT8 ConvRot et VAE Qwen 2.1. Il s'agit de la version locale quantifiée fournie par l'auteur ; le Space utilise Diffusers avec le modèle BF16 et son LoRA.
Le script `setup_qwen_local.py` permet de reprendre les téléchargements et de vérifier leurs sommes SHA-256.
Le chargeur GGUF a reçu l'identifiant d'architecture `qwen_image21`, déjà géré par le cœur ComfyUI installé ; sa version précédente est sauvegardée dans `atelier_images/gguf_loader_before_qwen.py.bak`.
Le petit nœud `AtelierLoadReference` charge les PNG de référence avec Pillow pour respecter le contournement PyAV de cette installation. Aucune dépendance vidéo n'est nécessaire.

Le nom du modèle et le workflow sont enregistrés dans chaque PNG. **Reprendre cette idée** reprend aussi la référence de retouche si elle existe encore.

Tout fonctionne localement. Aucun compte, service distant ou téléchargement de modèle supplémentaire.
En cas d'erreur de démarrage, consulte `atelier_images/comfyui.log`. Fermer l'atelier ne ferme pas ComfyUI s'il tourne en arrière-plan.
