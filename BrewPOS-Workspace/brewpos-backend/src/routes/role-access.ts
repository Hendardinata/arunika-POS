import { Router } from 'express';
import { prisma } from '../db';
import { logActivity } from '../services/systemLogger';

const router = Router();

// Ambil semua menu aplikasi (untuk setup)
router.get('/menus', async (req, res) => {
  try {
    const menus = await prisma.appMenu.findMany();
    res.json(menus);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch app menus' });
  }
});

// Ambil hak akses untuk role tertentu
router.get('/:role', async (req, res) => {
  try {
    const { role } = req.params;
    const access = await prisma.roleAccess.findMany({
      where: { role },
      include: { appMenu: true }
    });
    res.json(access);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch role access' });
  }
});

// Update hak akses untuk role
router.put('/:role', async (req, res) => {
  try {
    const { role } = req.params;
    const { accesses, userId } = req.body; // array of { appMenuId, canView, canEdit }

    if (!Array.isArray(accesses)) {
      return res.status(400).json({ error: 'Invalid accesses data' });
    }

    // Upsert each access rule
    for (const item of accesses) {
      await prisma.roleAccess.upsert({
        where: {
          role_appMenuId: {
            role,
            appMenuId: item.appMenuId
          }
        },
        update: {
          canView: item.canView,
          canEdit: item.canEdit
        },
        create: {
          role,
          appMenuId: item.appMenuId,
          canView: item.canView,
          canEdit: item.canEdit
        }
      });
    }

    // Log the change
    await logActivity('UPDATE_ROLE_ACCESS', userId ? Number(userId) : undefined, `Updated access for role: ${role}`);

    res.json({ message: 'Role access updated successfully' });
  } catch (error) {
    console.error('Error updating role access:', error);
    res.status(500).json({ error: 'Failed to update role access' });
  }
});

// Buat app menu baru (hanya untuk dev/setup)
router.post('/menus', async (req, res) => {
  try {
    const { name, path, icon } = req.body;
    const menu = await prisma.appMenu.create({
      data: { name, path, icon }
    });
    res.status(201).json(menu);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create app menu' });
  }
});

export default router;
