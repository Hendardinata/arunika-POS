import { PrismaClient } from '@prisma/client';
const prisma = new PrismaClient();

async function main() {
  // Delete old paths
  const oldPaths = ['/logs', '/shifts'];
  
  for (const path of oldPaths) {
    const menus = await prisma.appMenu.findMany({ where: { path } });
    for (const menu of menus) {
      await prisma.roleAccess.deleteMany({ where: { appMenuId: menu.id } });
      await prisma.appMenu.delete({ where: { id: menu.id } });
      console.log(`Deleted old menu: ${path}`);
    }
  }

  // Ensure /operations exists
  let opMenu = await prisma.appMenu.findFirst({ where: { path: '/operations' } });
  if (!opMenu) {
    opMenu = await prisma.appMenu.create({
      data: { name: 'Operasional', path: '/operations' }
    });
    console.log(`Created new menu: /operations`);
  } else {
    // Update name just in case
    opMenu = await prisma.appMenu.update({
      where: { id: opMenu.id },
      data: { name: 'Operasional' }
    });
  }

  // Ensure all roles have access settings for it
  const roles = ['ADMIN', 'HEADBAR', 'CASHIER'];
  for (const role of roles) {
    const exists = await prisma.roleAccess.findUnique({
      where: {
        role_appMenuId: {
          role,
          appMenuId: opMenu.id
        }
      }
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
      console.log(`Added RoleAccess for ${role}`);
    }
  }

  console.log('Done cleaning up menus.');
}

main()
  .catch(e => console.error(e))
  .finally(async () => {
    await prisma.$disconnect();
  });
