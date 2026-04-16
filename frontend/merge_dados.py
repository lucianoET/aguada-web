import re

with open('/home/luc/Dev/aguada-web/frontend/dados.html', 'r', encoding='utf-8') as f:
    dados_content = f.read()

with open('/home/luc/Dev/aguada-web/frontend/balanco.html', 'r', encoding='utf-8') as f:
    balanco_content = f.read()

# Extract styles
dados_styles = re.search(r'<style>(.*?)</style>', dados_content, re.DOTALL).group(1)
balanco_styles = re.search(r'<style>(.*?)</style>', balanco_content, re.DOTALL).group(1)

# Combined styles
combined_styles = f"{dados_styles}\n{balanco_styles}"

# We can just manually combine them using write_to_file, it's easier to just build the whole file. 
