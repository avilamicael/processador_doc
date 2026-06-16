// Dados mock do design DocWatch (Opção B). Substituir por dados da API nas fases GSD.
import type { Automation, Doc, Folder, Integration, Rule, Template } from '../types'

export const DOCS: Doc[] = [
  { id: 1, name: 'NF-2024-00871.pdf', folder: '/Financeiro/Entradas', type: 'Nota Fiscal', tmpl: 'Nota Fiscal Eletrônica', status: 'tratado', size: '248 KB', date: '14 jun · 09:32', who: 'M. Almeida' },
  { id: 2, name: 'contrato-prestacao-acme.pdf', folder: '/Jurídico/Contratos', type: 'Contrato', tmpl: 'Contrato Padrão', status: 'leitura', size: '1.2 MB', date: '14 jun · 09:30', who: '—' },
  { id: 3, name: 'boleto-energia-05-2026.pdf', folder: '/Financeiro/Boletos', type: 'Boleto', tmpl: 'Boleto Bancário', status: 'tratado', size: '96 KB', date: '14 jun · 08:58', who: 'R. Costa' },
  { id: 4, name: 'holerite-maio-2026.pdf', folder: '/RH/Folha', type: 'Holerite', tmpl: 'Holerite', status: 'erro', size: '512 KB', date: '14 jun · 08:40', who: 'Sistema' },
  { id: 5, name: 'nf-servico-3320.pdf', folder: '/Financeiro/Entradas', type: 'Nota Fiscal', tmpl: 'Nota Fiscal Eletrônica', status: 'encontrado', size: '180 KB', date: '14 jun · 08:33', who: '—' },
  { id: 6, name: 'apolice-seguro-frota.pdf', folder: '/Operações/Seguros', type: 'Apólice', tmpl: 'Apólice de Seguro', status: 'tratado', size: '2.4 MB', date: '13 jun · 18:21', who: 'J. Pereira' },
  { id: 7, name: 'comprovante-pix-4471.pdf', folder: '/Financeiro/Comprovantes', type: 'Comprovante', tmpl: 'Comprovante de Pagamento', status: 'tratado', size: '64 KB', date: '13 jun · 17:05', who: 'R. Costa' },
  { id: 8, name: 'contrato-locacao-sala12.pdf', folder: '/Jurídico/Contratos', type: 'Contrato', tmpl: 'Contrato Padrão', status: 'leitura', size: '880 KB', date: '13 jun · 16:48', who: '—' },
  { id: 9, name: 'fatura-cartao-corp-04.pdf', folder: '/Financeiro/Cartões', type: 'Fatura', tmpl: 'Fatura de Cartão', status: 'encontrado', size: '320 KB', date: '13 jun · 15:30', who: '—' },
  { id: 10, name: 'recibo-3219.pdf', folder: '/Financeiro/Recibos', type: 'Recibo', tmpl: '—', status: 'erro', size: '48 KB', date: '13 jun · 14:12', who: 'Sistema' },
  { id: 11, name: 'nota-debito-1180.pdf', folder: '/Financeiro/Entradas', type: 'Nota de Débito', tmpl: 'Nota Fiscal Eletrônica', status: 'tratado', size: '132 KB', date: '13 jun · 11:44', who: 'M. Almeida' },
  { id: 12, name: 'termo-aditivo-acme.pdf', folder: '/Jurídico/Contratos', type: 'Aditivo', tmpl: 'Contrato Padrão', status: 'tratado', size: '410 KB', date: '13 jun · 10:02', who: 'J. Pereira' },
]

export const FOLDERS: Folder[] = [
  { id: 1, path: '/Financeiro/Entradas', rec: true, types: 'PDF', freq: 'A cada 5 min', last: 'há 2 min', files: '1.842' },
  { id: 2, path: '/Jurídico/Contratos', rec: true, types: 'PDF', freq: 'A cada 15 min', last: 'há 12 min', files: '514' },
  { id: 3, path: '/RH/Folha', rec: false, types: 'PDF', freq: 'A cada 1 h', last: 'há 40 min', files: '128' },
  { id: 4, path: '/Operações/Seguros', rec: true, types: 'PDF, PDF/A', freq: 'Diária · 02:00', last: 'ontem 02:00', files: '96' },
]

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

export const STATUS_LABELS: Record<string, string> = {
  encontrado: 'Encontrado',
  leitura: 'Em leitura',
  tratado: 'Tratado',
  erro: 'Erro',
}
