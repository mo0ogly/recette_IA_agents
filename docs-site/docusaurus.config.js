// @ts-check
// Docusaurus config for the inspect_ia_agents (Railgun) documentation site.
// Surfaces the existing product docs under ../docs (runbooks, architecture,
// ADRs, migration provenance). Internal design plans (docs/plans), the
// gitignored tracking dir, and screenshots are excluded from the doc tree.
// See: https://docusaurus.io/docs/api/docusaurus-config

import {themes as prismThemes} from 'prism-react-renderer';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'inspect_ia_agents',
  tagline: 'Runtime governance layer for AI agents - recette + discovery',
  favicon: 'img/favicon.ico',

  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  url: 'https://inspect-ia-agents.tech',
  baseUrl: '/',

  organizationName: 'inspect_ia_agents',
  projectName: 'recette_agentrail',

  // Runbooks link out to ../rules/*.md and other repo files outside the doc
  // tree; warn instead of failing the build on those cross-tree links.
  onBrokenLinks: 'warn',

  markdown: {
    mermaid: true,
    // Product docs are CommonMark with raw <placeholder> / {json} snippets that
    // would break MDX parsing; process .md as plain Markdown, not MDX.
    format: 'md',
    hooks: {
      onBrokenMarkdownLinks: 'warn',
      // i18n/en mirror docs keep relative ../screenshots paths that only resolve
      // from the default-locale docs/ tree; warn instead of failing the build.
      onBrokenMarkdownImages: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'fr',
    locales: ['fr', 'en'],
    localeConfigs: {
      fr: {label: 'Francais', htmlLang: 'fr-FR'},
      en: {label: 'English', htmlLang: 'en-US'},
    },
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          // Source of truth = the repo's existing docs/ tree (not a copy).
          path: '../docs',
          routeBasePath: 'docs',
          sidebarPath: './sidebars.js',
          // Product-doc scope: exclude internal plans, tracking, screenshots.
          exclude: [
            'plans/**',
            'tracking/**',
            'screenshots/**',
            '**/_*.{js,jsx,ts,tsx,md,mdx}',
            '**/node_modules/**',
          ],
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        defaultMode: 'dark',
        respectPrefersColorScheme: true,
      },
      mermaid: {
        theme: {light: 'dark', dark: 'dark'},
      },
      navbar: {
        title: 'inspect_ia_agents',
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Docs',
          },
          {
            to: '/docs/ARCHITECTURE',
            label: 'Architecture',
            position: 'left',
          },
          {
            type: 'localeDropdown',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {label: 'Architecture', to: '/docs/ARCHITECTURE'},
              {label: 'Platform runbook', to: '/docs/runbooks/platform'},
              {label: 'Installation', to: '/docs/runbooks/installation'},
            ],
          },
        ],
        copyright: `Copyright ${new Date().getFullYear()} inspect_ia_agents. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

export default config;
