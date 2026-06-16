// Dados mock do design DocWatch (Opção B). Substituir por dados da API nas fases GSD.
// Fase 2 (02-05): DOCS/FOLDERS/STATUS_LABELS removidos — Documentos e Pastas usam
// dados reais via TanStack Query (src/hooks/*). Os arrays abaixo pertencem a telas
// de fases futuras (Templates/Automações/Integrações/Regras) ainda não fiadas.
import type { Automation, Integration, Rule, Template } from '../types'

export const RULES: Rule[] = [
  { id: 1, name: 'Por marcador QR Code', param: 'SEP-DOC', desc: 'Divide o lote sempre que detecta um QR Code de separação na página.' },
  { id: 2, name: 'Por número de páginas', param: 'a cada 1 pág.', desc: 'Cria um novo documento a cada N páginas do PDF de origem.' },
  { id: 3, name: 'Por texto âncora', param: '“NOTA FISCAL”', desc: 'Inicia um novo documento ao encontrar um texto-chave no topo da página.' },
  { id: 4, name: 'Por página em branco', param: 'sens. 98%', desc: 'Usa páginas em branco como separadores entre documentos.' },
]

export const INTEGRATIONS: Integration[] = [
  { id: 1, name: 'Google Drive', cat: 'Armazenamento', mono: 'GD', on: true },
  { id: 2, name: 'SharePoint', cat: 'Armazenamento', mono: 'SP', on: true },
  { id: 3, name: 'Amazon S3', cat: 'Armazenamento', mono: 'S3', on: false },
  { id: 4, name: 'ERP Omie', cat: 'Gestão', mono: 'OM', on: true },
  { id: 5, name: 'Webhook', cat: 'Integração', mono: '{}', on: true },
  { id: 6, name: 'E-mail (SMTP)', cat: 'Notificação', mono: '@', on: true },
]

export const TEMPLATES: Template[] = [
  { name: 'Nota Fiscal Eletrônica', type: 'Fiscal', fields: ['CNPJ emitente', 'Número', 'Valor total', 'Data de emissão', 'CFOP'], docs: '1.284', rule: 'Texto âncora' },
  { name: 'Contrato Padrão', type: 'Jurídico', fields: ['Partes', 'Objeto', 'Vigência', 'Valor'], docs: '312', rule: 'QR Code' },
  { name: 'Boleto Bancário', type: 'Financeiro', fields: ['Linha digitável', 'Vencimento', 'Valor', 'Beneficiário'], docs: '906', rule: 'Texto âncora' },
  { name: 'Apólice de Seguro', type: 'Operações', fields: ['Seguradora', 'Nº apólice', 'Vigência', 'Prêmio'], docs: '88', rule: 'Por páginas' },
  { name: 'Comprovante de Pagamento', type: 'Financeiro', fields: ['Valor', 'Data', 'ID transação'], docs: '540', rule: 'Página em branco' },
  { name: 'Holerite', type: 'RH', fields: ['Competência', 'Salário', 'Descontos', 'Líquido'], docs: '274', rule: 'Por páginas' },
]

export const AUTOMATIONS: Automation[] = [
  { id: 1, name: 'Indexar Nota Fiscal no ERP', trigger: 'Documento tratado', cond: 'Template = Nota Fiscal', action: 'Enviar ao ERP Omie', runs: '1.284 execuções' },
  { id: 2, name: 'Arquivar contratos assinados', trigger: 'Documento tratado', cond: 'Template = Contrato', action: 'Mover p/ Jurídico + notificar', runs: '312 execuções' },
  { id: 3, name: 'Alerta de falha de leitura', trigger: 'Status = Erro', cond: 'Qualquer documento', action: 'E-mail ao responsável', runs: '47 execuções' },
  { id: 4, name: 'Webhook de boletos', trigger: 'Documento tratado', cond: 'Template = Boleto', action: 'POST p/ endpoint financeiro', runs: 'Pausada' },
  { id: 5, name: 'Renomear pelo padrão', trigger: 'Documento tratado', cond: 'Qualquer documento', action: 'Renomear {tipo}-{nº}-{data}', runs: '3.140 execuções' },
]
