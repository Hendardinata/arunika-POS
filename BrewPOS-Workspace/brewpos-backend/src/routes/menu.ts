import { Router } from 'express';
import { prisma } from '../db';
import { logActivity } from '../services/systemLogger';
import multer from 'multer';
import path from 'path';
import fs from 'fs';

const router = Router();

// Ensure uploads directory exists
const uploadDir = path.join(__dirname, '../../public/uploads');
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, uniqueSuffix + path.extname(file.originalname));
  }
});
const upload = multer({ storage });

// Get all menus
router.get('/', async (req, res) => {
  try {
    const itemQuantities = await prisma.transactionItem.groupBy({
      by: ['menuId'],
      _sum: {
        quantity: true
      }
    });
    
    const quantityMap = new Map(itemQuantities.map(item => [item.menuId, item._sum.quantity || 0]));

    const menus = await prisma.menu.findMany({
      include: { category: true },
    });
    
    const menusWithSoldCount = menus.map(menu => ({
      ...menu,
      soldCount: quantityMap.get(menu.id) || 0
    }));

    res.json(menusWithSoldCount);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch menus' });
  }
});

// Create menu
router.post('/', upload.single('image'), async (req, res) => {
  try {
    const { name, description, price, categoryId, hpp } = req.body;
    let imageUrl = null;
    
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
    } else if (req.body.imageUrl) {
      imageUrl = req.body.imageUrl;
    }

    const menu = await prisma.menu.create({
      data: {
        name,
        description,
        price: Number(price),
        hpp: hpp !== undefined ? Number(hpp) : 0,
        categoryId: Number(categoryId),
        imageUrl
      },
    });
    
    await logActivity('CREATE_MENU', req.headers['x-user-id'] ? Number(req.headers['x-user-id']) : undefined, `Created menu: ${name}`, 'Menu', menu.id);
    
    res.status(201).json(menu);
  } catch (error) {
    console.error('Error creating menu:', error);
    res.status(500).json({ error: 'Failed to create menu', details: error instanceof Error ? error.message : String(error) });
  }
});

// Update menu
router.put('/:id', upload.single('image'), async (req, res) => {
  try {
    const { id } = req.params;
    const { name, description, price, categoryId, hpp } = req.body;
    
    // Find existing menu to check current image if no new one provided
    const existingMenu = await prisma.menu.findUnique({ where: { id: Number(id) } });
    if (!existingMenu) {
      return res.status(404).json({ error: 'Menu not found' });
    }

    let imageUrl = existingMenu.imageUrl;
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
    } else if (req.body.imageUrl !== undefined) {
      imageUrl = req.body.imageUrl;
    }

    const menu = await prisma.menu.update({
      where: { id: Number(id) },
      data: {
        name,
        description,
        price: Number(price),
        hpp: hpp !== undefined ? Number(hpp) : existingMenu.hpp,
        categoryId: Number(categoryId),
        imageUrl
      },
    });

    await logActivity('UPDATE_MENU', req.headers['x-user-id'] ? Number(req.headers['x-user-id']) : undefined, `Updated menu: ${menu.name}`, 'Menu', menu.id);

    res.json(menu);
  } catch (error) {
    console.error('Error updating menu:', error);
    res.status(500).json({ error: 'Failed to update menu', details: error instanceof Error ? error.message : String(error) });
  }
});

// Delete menu
router.delete('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    
    // Check if menu exists
    const menu = await prisma.menu.findUnique({ where: { id: Number(id) } });
    if (!menu) {
      return res.status(404).json({ error: 'Menu not found' });
    }

    // Try deleting the menu
    // If it's used in transactions, Prisma will throw a foreign key constraint error
    await prisma.menu.delete({
      where: { id: Number(id) },
    });

    await logActivity('DELETE_MENU', req.headers['x-user-id'] ? Number(req.headers['x-user-id']) : undefined, `Deleted menu: ${menu.name}`, 'Menu', menu.id);

    res.status(204).send();
  } catch (error: any) {
    console.error('Error deleting menu:', error);
    // Prisma Foreign Key Constraint Failed Error Code: P2003
    if (error.code === 'P2003') {
      res.status(400).json({ error: 'Cannot delete menu because it is already used in transactions. Please hide or disable it instead (feature coming soon).' });
    } else {
      res.status(500).json({ error: 'Failed to delete menu', details: error.message });
    }
  }
});

export default router;
