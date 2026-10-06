import {basicCatalog} from '@a2ui/react/v0_9';
import type {A2uiMessage} from '@a2ui/web_core/v0_9';

const SURFACE_ID = 'welcome';

/** 首页欢迎 Surface：三个金融业务入口。 */
export const welcomeMessages: A2uiMessage[] = [
  {
    version: 'v0.9',
    createSurface: {
      surfaceId: SURFACE_ID,
      catalogId: basicCatalog.id,
    },
  },
  {
    version: 'v0.9',
    updateComponents: {
      surfaceId: SURFACE_ID,
      components: [
        {id: 'root', component: 'Column', children: ['title', 'subtitle', 'divider', 'services']},
        {id: 'title', component: 'Text', text: {path: '/title'}, variant: 'h2'},
        {id: 'subtitle', component: 'Text', text: {path: '/subtitle'}, variant: 'body'},
        {id: 'divider', component: 'Divider'},
        {
          id: 'services',
          component: 'Row',
          children: ['card-transfer', 'card-invest', 'card-balance'],
          justify: 'spaceBetween',
        },
        {id: 'card-transfer', component: 'Card', child: 'col-transfer'},
        {
          id: 'col-transfer',
          component: 'Column',
          children: ['icon-transfer', 'name-transfer', 'desc-transfer', 'btn-transfer'],
        },
        {id: 'icon-transfer', component: 'Icon', name: 'payment'},
        {id: 'name-transfer', component: 'Text', text: {path: '/transfer/name'}, variant: 'h4'},
        {id: 'desc-transfer', component: 'Text', text: {path: '/transfer/desc'}, variant: 'caption'},
        {
          id: 'btn-transfer',
          component: 'Button',
          child: 'btn-transfer-label',
          variant: 'primary',
          action: {
            event: {
              name: 'start_service',
              context: {query: {path: '/transfer/query'}},
            },
          },
        },
        {id: 'btn-transfer-label', component: 'Text', text: {path: '/transfer/action'}},
        {id: 'card-invest', component: 'Card', child: 'col-invest'},
        {
          id: 'col-invest',
          component: 'Column',
          children: ['icon-invest', 'name-invest', 'desc-invest', 'btn-invest'],
        },
        {id: 'icon-invest', component: 'Icon', name: 'shoppingCart'},
        {id: 'name-invest', component: 'Text', text: {path: '/invest/name'}, variant: 'h4'},
        {id: 'desc-invest', component: 'Text', text: {path: '/invest/desc'}, variant: 'caption'},
        {
          id: 'btn-invest',
          component: 'Button',
          child: 'btn-invest-label',
          variant: 'primary',
          action: {
            event: {
              name: 'start_service',
              context: {query: {path: '/invest/query'}},
            },
          },
        },
        {id: 'btn-invest-label', component: 'Text', text: {path: '/invest/action'}},
        {id: 'card-balance', component: 'Card', child: 'col-balance'},
        {
          id: 'col-balance',
          component: 'Column',
          children: ['icon-balance', 'name-balance', 'desc-balance', 'btn-balance'],
        },
        {id: 'icon-balance', component: 'Icon', name: 'accountCircle'},
        {id: 'name-balance', component: 'Text', text: {path: '/balance/name'}, variant: 'h4'},
        {id: 'desc-balance', component: 'Text', text: {path: '/balance/desc'}, variant: 'caption'},
        {
          id: 'btn-balance',
          component: 'Button',
          child: 'btn-balance-label',
          variant: 'primary',
          action: {
            event: {
              name: 'start_service',
              context: {query: {path: '/balance/query'}},
            },
          },
        },
        {id: 'btn-balance-label', component: 'Text', text: {path: '/balance/action'}},
      ],
    },
  },
  {
    version: 'v0.9',
    updateDataModel: {
      surfaceId: SURFACE_ID,
      path: '/',
      value: {
        title: '金融智能体',
        subtitle: '选择一项服务，或在下方直接输入需求。支持转账、理财和余额查询。',
        transfer: {
          name: '转账服务',
          desc: '向指定账户转账',
          action: '开始转账',
          query: '我要转账',
        },
        invest: {
          name: '理财服务',
          desc: '推荐并购买理财产品',
          action: '开始理财',
          query: '我要理财',
        },
        balance: {
          name: '余额查询',
          desc: '查询账户余额',
          action: '开始查询',
          query: '查询余额',
        },
      },
    },
  },
];
