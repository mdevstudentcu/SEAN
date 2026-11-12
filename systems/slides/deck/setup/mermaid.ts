import { defineMermaidSetup } from '@slidev/types'

export default defineMermaidSetup(() => ({
  theme: 'base',
  themeVariables: {
    darkMode: true,
    background: '#1b2128',
    primaryColor: '#2b343d',
    primaryTextColor: '#eef1f4',
    primaryBorderColor: '#8a96a3',
    secondaryColor: '#232b33',
    tertiaryColor: '#232b33',
    lineColor: '#8a96a3',
    clusterBkg: '#20272e',
    clusterBorder: '#5b6672',
    fontFamily: 'Red Hat Text, Arial, sans-serif',
    fontSize: '17px',
  },
  flowchart: { curve: 'basis', padding: 14, nodeSpacing: 34, rankSpacing: 46 },
}))
