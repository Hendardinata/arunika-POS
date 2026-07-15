import { Router } from 'express';
import { prisma } from '../db';

const router = Router();

// Get all menus with their recipe notes
router.get('/', async (req, res) => {
  try {
    const menus = await prisma.menu.findMany();
    res.json(menus);
  } catch (error) {
    console.error('Error fetching recipes:', error);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// Update recipe notes for a specific menu
router.post('/:menuId', async (req, res) => {
  const menuId = parseInt(req.params.menuId);
  const { recipeNotes } = req.body;

  try {
    await prisma.menu.update({
      where: { id: menuId },
      data: { recipeNotes }
    });

    res.json({ message: 'Recipe updated successfully' });
  } catch (error) {
    console.error('Error updating recipe:', error);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

export default router;
