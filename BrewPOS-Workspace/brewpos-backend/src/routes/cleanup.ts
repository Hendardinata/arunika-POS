import express from 'express';
import { prisma } from '../db';

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const oldPaths = ['/logs', '/shifts'];
    for (const path of oldPaths) {
      const menus = await prisma.appMenu.findMany({ where: { path } });
      for (const menu of menus) {
        await prisma.roleAccess.deleteMany({ where: { appMenuId: menu.id } });
        await prisma.appMenu.delete({ where: { id: menu.id } });
      }
    }

    let opMenu = await prisma.appMenu.findFirst({ where: { path: '/operations' } });
    if (!opMenu) {
      opMenu = await prisma.appMenu.create({
        data: { name: 'Operasional', path: '/operations' }
      });
    } else {
      opMenu = await prisma.appMenu.update({
        where: { id: opMenu.id },
        data: { name: 'Operasional' }
      });
    }

    const roles = ['ADMIN', 'HEADBAR', 'CASHIER'];
    for (const role of roles) {
      const exists = await prisma.roleAccess.findUnique({
        where: { role_appMenuId: { role, appMenuId: opMenu.id } }
      });
      if (!exists) {
        await prisma.roleAccess.create({
          data: {
            role,
            appMenuId: opMenu.id,
            canView: role === 'ADMIN',
            canEdit: role === 'ADMIN'
          }
        });
      }
    }
    res.send('Cleanup done');
  } catch (e) {
    console.error(e);
    res.status(500).send(String(e));
  }
});

export default router;
